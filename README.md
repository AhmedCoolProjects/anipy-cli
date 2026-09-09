# ANIPY-CLI
**Anime from the comfort of your Terminal**
<p align="center"><img src="https://github.com/sdaqo/anipy-cli/assets/63876564/1dafa5fb-4273-4dc1-a7ab-2664dd668fc9" /> </p>

## What even is this?
A little tool written in python to watch and download anime from the terminal (the better way to watch anime).
This project's main aim is to create an enjoyable experience watching and downloading anime, directly from the terminal - your favorite place.

**Features include: Seaonals mode, AniList and MyAnimeList integration, custom post-download scripts, automatic remuxing, discord presence and many more! You can even use your own files instead of online anime sites!**

Since the version 3 rewrite this project is split into api and frontend. This makes it easy to integrate anipy-cli into your own project!

---

## ⚡ Ahmed's Fork Features & Improvements

This fork contains fixes and feature additions for everyday use:

- **🛡️ DNS-over-HTTPS (DoH) Bypass:** Patched socket resolution to use Cloudflare / Google DoH automatically, bypassing ISP/regional domain blocking on streaming CDNs.
- **🌍 Arabic Subtitle Support:** Automatic subtitle scraping and caching from SubDL for every episode if not provided by the stream source.
- **🎬 HiAnime Provider:** Fixed streaming provider scraping `hianime.at` with XOR stream decryption (`otaku-embed-v1`) and external subtitle extraction.
- **🔧 AllAnime Provider Fix:** Inline GraphQL queries and fallback keygen logic when remote query hashes fail.
- **📺 IINA & MPV Player Enhancements:** Seamless IINA player integration on macOS with proper subtitle forwarding (`--mpv-sub-files`), and MPV subtitle language preference (`--slang=ara,ar,eng,en`).
- **🚀 Resilient Search:** Graceful error handling across search providers so one failing provider doesn't abort the search.

---

## 📦 Installation on Any Machine

### 1. Install Prerequisites

**macOS:**
```bash
# Install video player (IINA or MPV) and pipx
brew install --cask iina
brew install mpv ffmpeg pipx
pipx ensurepath
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt update && sudo apt install -y mpv ffmpeg pipx python3-pip
pipx ensurepath
```

### 2. Install this Fork

Install both the patched API and the CLI directly using `pipx`:

```bash
# Option A: Directly from GitHub
pip install "git+https://github.com/AhmedCoolProjects/anipy-cli.git#subdirectory=api"
pipx install "git+https://github.com/AhmedCoolProjects/anipy-cli.git#subdirectory=cli"
```

Or by cloning locally:
```bash
# Option B: From a local clone
git clone https://github.com/AhmedCoolProjects/anipy-cli.git
cd anipy-cli
pip install ./api
pipx install ./cli
```

### 3. Configure Video Player

Run `anipy-cli -v` once to generate the default configuration file:
```bash
anipy-cli -v
```

To set **IINA** as default player (macOS):
```bash
# macOS
sed -i '' 's/^player_path: .*/player_path: iina/' "$HOME/Library/Application Support/anipy-cli/config.yaml"
```

Or to use **MPV**:
```bash
# macOS
sed -i '' 's/^player_path: .*/player_path: mpv/' "$HOME/Library/Application Support/anipy-cli/config.yaml"

# Linux
sed -i 's/^player_path: .*/player_path: mpv/' "$HOME/.config/anipy-cli/config.yaml"
```

---

## 🎮 Quick Usage Guide

```bash
# Interactive menu
anipy-cli

# Direct search & watch (format: query:episode:type)
anipy-cli -s "frieren:1:sub"

# Binge mode (multiple episodes)
anipy-cli -B -s "attack on titan:1-5:sub"

# Watch history
anipy-cli -H

# Download episodes
anipy-cli -D -s "naruto:1-3:sub"

# Override player on the fly (-p iina / -p mpv / -p vlc)
anipy-cli -p iina
```
## You are just here for the client?
<a href="https://pypi.org/project/anipy-cli/"><img alt="PyPI - Version" src="https://img.shields.io/pypi/v/anipy-cli?style=for-the-badge&logo=pypi&label=anipy-cli"></a>

As one wise man once said:
> I DONT GIVE A FUCK ABOUT THE FUCKING CODE! i just want to download this stupid fucking application and use it.
>
> WHY IS THERE CODE??? MAKE A FUCKING .EXE FILE AND GIVE IT TO ME. these dumbfucks think that everyone is a developer and understands code. well i am not and i don't understand it. I only know to download and install applications. SO WHY THE FUCK IS THERE CODE? make an EXE file and give it to me. STUPID FUCKING SMELLY NERDS

<sub>Please do not take this seriously this is some stupid copypasta</sub>

We do not have an .exe, but we have pipx: `pipx install anipy-cli`

Check out [Getting Started - CLI](https://sdaqo.github.io/anipy-cli/getting-started-cli) for more installation options (pip, nix) and advice!

## You want to use the api for your project?
<a href="https://pypi.org/project/anipy-api/"><img alt="PyPI - Version" src="https://img.shields.io/pypi/v/anipy-api?style=for-the-badge&logo=pypi&label=anipy-api"></a>

Please check out [Getting Started - API](https://sdaqo.github.io/anipy-cli/getting-started-api) for instructions.


## :heart: Credits! 

#### Heavily inspired by https://github.com/pystardust/ani-cli/

#### All contributors for contributing

<a href="https://github.com/sdaqo/anipy-cli/graphs/contributors">
    <img src="https://contrib.rocks/image?repo=sdaqo/anipy-cli" alt="anipy-cli contributors" title="anipy-cli contributors" width="800"/>
</a>

If you want to contribute as well, check this out: https://sdaqo.github.io/anipy-cli/contributing

---

[Legal Disclaimer](DISCLAIMER.md)
