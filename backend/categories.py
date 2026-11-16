# Maps an app or website to a category. The categories are what the analytics and the
# nudges reason about ("social", "video", "coding", ...), so edit these lists to match
# the apps you actually use. Rules are checked in order: site first, then app name, then title.

SITES = {
    "social": ["reddit.com", "twitter.com", "x.com", "instagram.com", "facebook.com", "tiktok.com",
               "threads.net", "bsky.app", "linkedin.com", "tumblr.com", "news.ycombinator.com",
               "9gag.com", "pinterest.com"],
    "video": ["youtube.com", "youtu.be", "twitch.tv", "netflix.com", "hulu.com", "disneyplus.com",
              "primevideo.com", "vimeo.com", "max.com"],
    "chat": ["discord.com", "web.whatsapp.com", "messenger.com", "slack.com", "web.telegram.org",
             "teams.microsoft.com"],
    "coding": ["github.com", "gitlab.com", "stackoverflow.com", "leetcode.com", "codepen.io",
               "colab.research.google.com", "kaggle.com"],
    "docs": ["docs.google.com", "notion.so", "overleaf.com", "office.com", "chatgpt.com",
             "claude.ai", "wikipedia.org", "arxiv.org"],
    "email": ["mail.google.com", "outlook.live.com", "outlook.office.com"],
    "shopping": ["amazon.com", "ebay.com", "etsy.com", "aliexpress.com"],
    "news": ["nytimes.com", "bbc.com", "cnn.com", "theguardian.com", "reuters.com"],
}

APPS = {
    "coding": ["code", "visual studio code", "cursor", "pycharm", "intellij", "xcode", "sublime",
               "vim", "nvim", "neovim", "emacs", "zed", "android studio", "webstorm",
               "terminal", "iterm", "iterm2", "warp", "alacritty", "kitty", "wezterm",
               "windowsterminal", "powershell", "cmd", "gnome-terminal", "konsole"],
    "chat": ["discord", "slack", "whatsapp", "telegram", "messages", "signal", "teams", "zoom"],
    "video": ["vlc", "iina", "quicktime player", "netflix", "mpv"],
    "music": ["spotify", "music", "apple music"],
    "games": ["steam", "minecraft", "league of legends", "valorant", "roblox", "epic games"],
    "docs": ["notion", "obsidian", "word", "microsoft word", "pages", "preview", "acrobat",
             "excel", "numbers", "powerpoint", "keynote", "onenote", "zotero"],
    "email": ["mail", "outlook", "thunderbird", "spark"],
}

# keywords for browser window titles when the URL can't be read (Windows / Linux)
TITLE_KEYWORDS = {
    "reddit.com": ["reddit"],
    "youtube.com": ["youtube"],
    "x.com": [" / x", "on x:", "twitter"],
    "instagram.com": ["instagram"],
    "tiktok.com": ["tiktok"],
    "twitch.tv": ["twitch"],
    "netflix.com": ["netflix"],
    "discord.com": ["discord"],
    "github.com": ["github"],
    "stackoverflow.com": ["stack overflow"],
    "docs.google.com": ["google docs", "google sheets"],
    "mail.google.com": ["gmail"],
    "facebook.com": ["facebook"],
    "linkedin.com": ["linkedin"],
    "news.ycombinator.com": ["hacker news"],
}

BROWSERS = ["google chrome", "chrome", "chromium", "safari", "firefox", "arc", "brave browser",
            "brave", "microsoft edge", "msedge", "opera", "vivaldi", "zen"]


def is_browser(app):
    return (app or "").lower().removesuffix(".exe") in BROWSERS


def site_from_title(title):
    title = (title or "").lower()
    for site, words in TITLE_KEYWORDS.items():
        if any(w in title for w in words):
            return site
    return None


def normalize_domain(domain):
    domain = (domain or "").lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    if domain.startswith("m."):
        domain = domain[2:]
    return domain or None


def categorize(app, domain=None, title=None):
    app_l = (app or "").lower().removesuffix(".exe")
    domain = normalize_domain(domain)
    if domain:
        for category, sites in SITES.items():
            if any(domain == s or domain.endswith("." + s) for s in sites):
                return category
    if is_browser(app_l):
        return "browsing"
    for category, apps in APPS.items():
        if app_l in apps:
            return category
    return "other"
