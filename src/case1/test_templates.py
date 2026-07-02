import os
import unittest


BASE_DIR = os.path.dirname(__file__)
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STYLE_PATH = os.path.join(BASE_DIR, "static", "css", "app.css")


class TemplatePolishTest(unittest.TestCase):
    def read_template(self, name):
        with open(os.path.join(TEMPLATE_DIR, name), "r", encoding="utf-8") as file:
            return file.read()

    def test_pages_use_shared_app_shell_styles(self):
        for template in ["index.html", "users.html", "attendance.html"]:
            html = self.read_template(template)
            self.assertIn('/static/css/app.css', html)
            self.assertIn('class="app-shell"', html)
            self.assertIn('class="topbar"', html)

    def test_shared_styles_define_project_visual_system(self):
        with open(STYLE_PATH, "r", encoding="utf-8") as file:
            css = file.read()

        self.assertIn('--brand-blue', css)
        self.assertIn('.panel', css)
        self.assertIn('.metric-card', css)
        self.assertIn('.camera-frame', css)

    def test_attendance_page_exposes_camera_and_status_panels(self):
        html = self.read_template("attendance.html")
        self.assertIn('class="camera-frame"', html)
        self.assertIn('class="status-strip"', html)
        self.assertIn('class="records-panel"', html)


if __name__ == "__main__":
    unittest.main()
