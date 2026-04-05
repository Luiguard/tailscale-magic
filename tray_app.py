import pystray
import threading
from PIL import Image, ImageDraw


class MagicTray:
    def __init__(self, on_show_dashboard, on_exit):
        self.on_show_dashboard = on_show_dashboard
        self.on_exit = on_exit
        self.icon = None

    def _create_image(self):
        # Create a simple icon (Circle with a star/dot)
        width = 64
        height = 64
        color1 = (6, 182, 212)  # Cyan
        color2 = (3, 5, 10)  # Dark

        image = Image.new("RGB", (width, height), color2)
        dc = ImageDraw.Draw(image)
        dc.ellipse([8, 8, 56, 56], fill=color1)
        dc.text((20, 20), "M", fill="white")
        return image

    def _on_clicked(self, icon, item):
        if str(item) == "Dashboard öffnen":
            self.on_show_dashboard()
        elif str(item) == "Beenden":
            icon.stop()
            self.on_exit()

    def run(self):
        image = self._create_image()
        # PIL can handle many formats, but svg might need a real icon.
        # For robustness, we use the generated one or a local png if exists.

        menu = pystray.Menu(
            pystray.MenuItem(
                "Dashboard öffnen", self._on_clicked, default=True
            ),
            pystray.MenuItem("Beenden", self._on_clicked),
        )

        self.icon = pystray.Icon(
            "Tailscale Magic", image, "Tailscale Magic", menu
        )
        if self.icon:
            self.icon.run()


def start_tray(on_show, on_exit):
    tray = MagicTray(on_show, on_exit)
    threading.Thread(target=tray.run, daemon=True).start()
    return tray
