from fastapi.templating import Jinja2Templates

# Feature folders ship their own template partials (included as e.g.
# "audio/tts_dashboard.html"), so they are searched after the shared templates/.
templates = Jinja2Templates(directory=["templates", "features/audio/templates"])
