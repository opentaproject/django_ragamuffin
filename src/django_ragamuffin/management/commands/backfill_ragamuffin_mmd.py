import time
from collections import defaultdict
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from django_ragamuffin.models import Assistant, MATHPIX_UPLOAD_SUFFIXES, OpenAIFile


class Command(BaseCommand):
    help = "Reprocess active PDF/image uploads whose cached MMD directory is missing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report affected uploads without changing files, the database, or remote stores.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Process at most this many content directories.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.0,
            help="Seconds to wait between Mathpix submissions (default: 0).",
        )
        parser.add_argument(
            "--assistant-base",
            help="Only process storage paths belonging to this assistant base.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        delay = options["delay"]
        if limit is not None and limit < 1:
            raise CommandError("--limit must be at least 1")
        if delay < 0:
            raise CommandError("--delay cannot be negative")

        groups = self._missing_mmd_groups(options.get("assistant_base"))
        if limit is not None:
            groups = groups[:limit]

        if not groups:
            self.stdout.write(self.style.SUCCESS("No active uploads are missing MMD artifacts."))
            return

        repaired = 0
        failures = []
        for index, (directory, rows) in enumerate(groups, start=1):
            source_row = next(
                (row for row in rows if self._source_path(row).is_file()),
                None,
            )
            owners = list(
                Assistant.objects.filter(vector_stores__files__in=rows)
                .distinct()
                .order_by("pk")
            )
            row_ids = ",".join(str(row.pk) for row in rows)
            owner_names = ",".join(owner.name for owner in owners) or "none"
            source = self._source_path(source_row) if source_row else None
            summary = (
                f"[{index}/{len(groups)}] path={directory} rows={row_ids} "
                f"assistants={owner_names} source={source or 'missing'}"
            )

            if options["dry_run"]:
                self.stdout.write(f"WOULD REPROCESS {summary}")
                continue
            if source_row is None:
                failures.append(f"{directory}: original file is missing")
                self.stderr.write(self.style.ERROR(f"SKIPPED {summary}: original file is missing"))
                continue
            if not owners:
                failures.append(f"{directory}: no directly owning assistant")
                self.stderr.write(
                    self.style.ERROR(f"SKIPPED {summary}: no directly owning assistant")
                )
                continue

            filename = source_row.name or source.name
            self.stdout.write(
                f"PROCESSING [{index}/{len(groups)}] file={filename} path={directory}"
            )
            self.stdout.flush()
            try:
                for owner in owners:
                    with source.open("rb") as handle:
                        owner.add_file(filename, File(handle, name=filename))
                if not (directory / "mmd").is_dir():
                    raise RuntimeError("processing completed without creating the MMD directory")
            except Exception as exc:
                failures.append(f"{directory}: {exc}")
                self.stderr.write(self.style.ERROR(f"FAILED {summary}: {exc}"))
                continue

            repaired += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"DONE [{index}/{len(groups)}] file={filename} path={directory}"
                )
            )
            self.stdout.flush()
            if delay and index < len(groups):
                time.sleep(delay)

        action = "would reprocess" if options["dry_run"] else "repaired"
        count = len(groups) if options["dry_run"] else repaired
        self.stdout.write(f"Summary: {action} {count} content director{'y' if count == 1 else 'ies'}.")
        if failures:
            raise CommandError(
                f"Backfill completed with {len(failures)} failure(s); rerun after correcting them."
            )

    @staticmethod
    def _source_path(row):
        if row is None or not row.file:
            return Path("")
        return Path(row.file.path)

    def _missing_mmd_groups(self, assistant_base):
        grouped = defaultdict(list)
        rows = (
            OpenAIFile.objects.filter(vector_stores__isnull=False)
            .distinct()
            .order_by("-pk")
        )
        for row in rows:
            source = self._source_path(row)
            if source.suffix.lower() not in MATHPIX_UPLOAD_SUFFIXES:
                continue
            directory = Path(row.path) if row.path else source.parent
            if assistant_base:
                try:
                    relative = directory.relative_to(Path(row.file.storage.location))
                except (AttributeError, TypeError, ValueError):
                    relative = None
                if relative is None or not relative.parts or relative.parts[0] != assistant_base:
                    continue
            if (directory / "mmd").is_dir():
                continue
            grouped[directory].append(row)
        return sorted(grouped.items(), key=lambda item: str(item[0]))
