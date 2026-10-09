from django.test import SimpleTestCase

from django_ragamuffin.utils import mathfix, rewrite_query_image_links


class MathFixTests(SimpleTestCase):
    def test_mathpix_image_links_are_scoped_to_the_assistant(self):
        response = (
            "[Phase portrait](http://course.localhost:8000/"
            "django_ragamuffin/query/images/figure.jpg)\n\n"
            "![](./images/second.png)"
        )

        html = rewrite_query_image_links(mathfix(response), "course.branch")

        self.assertIn(
            'href="/django_ragamuffin/query/course/branch/images/figure.jpg"',
            html,
        )
        self.assertIn(
            'src="/django_ragamuffin/query/course/branch/images/second.png"',
            html,
        )

    def test_openai_latex_delimiters_are_protected_from_markdown(self):
        response = (
            r"Let \(t_1\) depend on \(v_{\max}\)." "\n\n"
            r"\[L_1=\frac12v_{\max}t_1.\]"
        )

        html = mathfix(response)

        self.assertNotIn("<em>", html)
        self.assertIn(r"$ t_1 $", html)
        self.assertIn(r"$ v_{\max} $", html)
        self.assertIn(r"\[  L_1=\frac12v_{\max}t_1.  \]", html)

    def test_fenced_text_block_keeps_lines_without_language_label(self):
        response = (
            "Using the exact input tokens, enter:\n\n"
            "```text\n"
            "v_max: (2*l1+l2)/T\n"
            "a: (2*l1+l2)^2/(2*T^2*l1)\n"
            "t_1: 2*l1*T/(2*l1+l2)\n"
            "```"
        )

        html = mathfix(response)

        self.assertIn('<pre>', html)
        self.assertIn('<code>', html)
        self.assertNotIn('<code>text', html)
        self.assertIn("v_max: (2*l1+l2)/T\n", html)
        self.assertIn("a: (2*l1+l2)^2/(2*T^2*l1)\n", html)
        self.assertIn("t_1: 2*l1*T/(2*l1+l2)\n", html)
