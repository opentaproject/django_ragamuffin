function setupBatchProgress(options) {
  const form = document.getElementById(options.formId);
  if (!form) {
    return;
  }

  form.addEventListener("submit", async function (event) {
    const items =
      options.itemType === "files"
        ? Array.from(form.querySelector(options.itemSelector).files)
        : Array.from(form.querySelectorAll(options.itemSelector));
    const total = items.length;
    if (!total) {
      return;
    }
    event.preventDefault();

    const operationId = crypto.randomUUID();
    const formData = new FormData(form);
    formData.append(options.idField, operationId);
    const progressContainer = document.getElementById(options.progressContainerId);
    const progress = document.getElementById(options.progressId);
    const progressText = document.getElementById(options.progressTextId);
    const controls = Array.from(form.querySelectorAll(options.controlsSelector));

    controls.forEach((control) => (control.disabled = true));
    progress.max = total;
    progress.value = 0;
    progressContainer.hidden = false;
    progressText.textContent = `0/${total} completed`;

    const statusUrl = `${window.location.pathname}${options.statusPath}/${operationId}/`;
    let polling = false;
    let failureResponse = {};

    async function reportClientEvent(clientStage, details = {}) {
      if (!options.failureReportField) {
        return;
      }
      const csrfToken = form.querySelector('[name="csrfmiddlewaretoken"]');
      const report = new URLSearchParams({
        [options.failureReportField]: "1",
        client_stage: clientStage,
        upload_id: operationId,
        files: JSON.stringify(
          items.map((item) => ({ name: item.name, size: item.size, type: item.type }))
        ),
        ...details,
      });
      if (csrfToken) {
        report.append("csrfmiddlewaretoken", csrfToken.value);
      }
      try {
        await fetch(form.action || window.location.href, {
          method: "POST",
          body: report,
          credentials: "same-origin",
          keepalive: true,
        });
      } catch (reportError) {
        console.error("Could not report upload failure", reportError);
      }
    }

    async function reportFailure(error) {
      await reportClientEvent("failed", {
        http_status: String(failureResponse.status || ""),
        status_text: failureResponse.statusText || "",
        response: failureResponse.body || "",
        error: String(error),
      });
    }

    async function updateProgress() {
      if (polling) {
        return;
      }
      polling = true;
      try {
        const response = await fetch(statusUrl, { credentials: "same-origin" });
        if (response.ok) {
          const status = await response.json();
          const completed = Math.min(status.completed, total);
          progress.value = completed;
          progressText.textContent = `${completed}/${total} completed`;
          if (status.failed) {
            progressText.textContent += ` — ${options.operationName} failed`;
          }
        }
      } catch (error) {
        console.error(error);
      } finally {
        polling = false;
      }
    }

    await reportClientEvent("started");
    const intervalId = window.setInterval(updateProgress, 1000);
    try {
      const response = await fetch(form.action || window.location.href, {
        method: "POST",
        body: formData,
        credentials: "same-origin",
      });
      if (!response.ok) {
        failureResponse = {
          status: response.status,
          statusText: response.statusText,
          body: (await response.text()).slice(0, 2000),
        };
        throw new Error(`${options.operationName} failed with status ${response.status}`);
      }

      await updateProgress();
      window.location.assign(response.url);
    } catch (error) {
      progressText.textContent = `${progress.value}/${total} completed — ${options.operationName} failed`;
      controls.forEach((control) => (control.disabled = false));
      console.error(error);
      await reportFailure(error);
    } finally {
      window.clearInterval(intervalId);
    }
  });
}
