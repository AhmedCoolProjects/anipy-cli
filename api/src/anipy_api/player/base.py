import atexit
import io
import os
import re
import subprocess as sp
import tempfile
import urllib.parse
import zipfile
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Optional, Protocol

from bs4 import BeautifulSoup
import requests
from anipy_api.error import PlayerError

SUB_DIR = os.path.expanduser('~/Library/Application Support/anipy-cli/subtitles')
os.makedirs(SUB_DIR, exist_ok=True)

def fetch_arabic_subtitle(title: str, ep: int, alt_titles=None) -> Optional[str]:
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', title)[:30]
    cached_prefix = f'{safe_name}_EP{ep}.ara.'
    try:
        for existing in os.listdir(SUB_DIR):
            if existing.startswith(cached_prefix):
                return os.path.join(SUB_DIR, existing)
    except Exception:
        pass

    queries = [title]
    if alt_titles:
        queries.extend(alt_titles)

    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 'Referer': 'https://subdl.com/'}

    for raw_title in queries:
        clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', raw_title)
        tokens = [t for t in clean.split() if len(t) > 1 and t.lower() not in ('the', 'of', 'an', 'and', 'in', 'to', 'no', 'wa', 'ga')]
        for q_str in (' '.join(tokens[:4]), ' '.join(tokens[:2])):
            if not q_str.strip():
                continue
            try:
                auto_url = f'https://api3.subdl.com/auto?query={urllib.parse.quote(q_str)}'
                r = requests.get(auto_url, headers=headers, timeout=4)
                results = r.json().get('results', [])
                if not results:
                    continue
                for res in results[:2]:
                    link = res.get('link')
                    if not link:
                        continue
                    for sub_path in (f'{link}/first-season/arabic', f'{link}/arabic', link):
                        r_page = requests.get(f'https://subdl.com{sub_path}', headers=headers, timeout=4)
                        if r_page.status_code != 200:
                            continue
                        soup = BeautifulSoup(r_page.text, 'html.parser')
                        candidates = []
                        for a in soup.find_all('a', href=lambda h: h and 'dl.subdl.com' in h):
                            node = a
                            text = ''
                            for _ in range(5):
                                node = node.parent
                                if node:
                                    text = node.text
                                    if any(k in text.lower() for k in ['e0', 'episode', 's01', f'- {ep:02d}', f'- {ep}']):
                                        break
                            clean_t = ' '.join(text.split())
                            if re.search(rf'\bE0?{ep}\b', clean_t, re.I) or re.search(rf'-\s*0?{ep}\b', clean_t) or re.search(rf'\bEpisode\s*0?{ep}\b', clean_t, re.I):
                                is_cr = 'crunchyroll' in clean_t.lower()
                                candidates.append((is_cr, a['href']))
                        if candidates:
                            candidates.sort(key=lambda c: c[0], reverse=True)
                            r_zip = requests.get(candidates[0][1], headers=headers, timeout=6)
                            z = zipfile.ZipFile(io.BytesIO(r_zip.content))
                            for fname in z.namelist():
                                if fname.endswith(('.srt', '.ass', '.vtt')):
                                    ext = fname.split('.')[-1]
                                    out_path = os.path.join(SUB_DIR, f'{safe_name}_EP{ep}.ara.{ext}')
                                    with open(out_path, 'wb') as f:
                                        f.write(z.read(fname))
                                    return out_path
            except Exception:
                continue
    return None

if TYPE_CHECKING:
    from anipy_api.anime import Anime
    from anipy_api.provider import ProviderStream

class PlayCallback(Protocol):
    """Callback that gets called upon playing a title, it accepts a anime and the stream being played."""

    def __call__(self, anime: "Anime", stream: "ProviderStream"):
        """
        Args:
            anime: The anime argument passed to the callback. This is the currently playing anime.
            stream: The stream argument passed to the callback. That is the currently playing stream.
        """
        ...


class PlayerBase(ABC):
    """The abstract base class for all the players.

    To list available players or get one by name, use
    [list_players][anipy_api.player.player.list_players]
    and [get_player][anipy_api.player.player.get_player] respectively.
    """

    def __init__(self, play_callback: Optional[PlayCallback] = None):
        """__init__ of PlayerBase

        Args:
            play_callback: Callback called upon starting to play a title with `play_title`
        """
        self._play_callback = play_callback

    @abstractmethod
    def play_title(self, anime: "Anime", stream: "ProviderStream"):
        """Play a stream of an anime.

        Args:
            anime: The anime
            stream: The stream
        """
        ...

    @abstractmethod
    def play_file(self, path: str):
        """Play any file.

        Args:
            path: The path to the file
        """
        ...

    @abstractmethod
    def wait(self):
        """Wait for the player to stop/close."""
        ...

    @abstractmethod
    def kill_player(self):
        """Kill the player."""
        ...

    def _call_play_callback(self, anime: "Anime", stream: "ProviderStream"):
        if self._play_callback:
            self._play_callback(anime, stream)

    @staticmethod
    def _get_media_title(anime: "Anime", stream: "ProviderStream"):
        return f"[{anime.provider.NAME}] {anime.name} E{stream.episode} [{stream.language}][{stream.resolution}p]"

    @staticmethod
    def _get_media_sub(stream: "ProviderStream", anime: Optional["Anime"] = None):
        subtitles = {}
        safe_title = re.sub(r'[^a-zA-Z0-9]', '_', anime.name)[:30] if anime and getattr(anime, "name", None) else "anime"
        if stream.subtitle:
            for name, sub in stream.subtitle.items():
                suffix = f".{sub.shortcode if sub.shortcode else 'und'}.{sub.codec}"
                out_file = os.path.join(SUB_DIR, f"{safe_title}_EP{stream.episode}{suffix}")
                try:
                    req = requests.get(sub.url, headers={"Referer": stream.referrer})
                    with open(out_file, "w", encoding="utf-8") as f:
                        f.write(req.content.decode("utf-8", "ignore"))
                    subtitles[name] = out_file
                except Exception:
                    pass

        # Always ensure Arabic subtitle is available
        has_arabic = any("ara" in k.lower() or "arabic" in k.lower() for k in subtitles.keys())
        if not has_arabic and anime and getattr(anime, "name", None):
            alts = getattr(anime, "alternative_names", None)
            ar_file = fetch_arabic_subtitle(anime.name, stream.episode, alts)
            if ar_file:
                subtitles["Arabic"] = ar_file

        return subtitles

class SubProcessPlayerBase(PlayerBase):
    """The base class for all players that are run through a sub process.

    For documentation of the other functions look at the [base class][anipy_api.player.base.PlayerBase].

    Example:
        Here is how you might implement such a player on your own:
        ```python
        class Mpv(SubProcessPlayerBase):
            def __init__(self, player_path: str, extra_args: List[str] = [], rpc_client=None):
                self.player_args_template = [ # (1)
                    "{stream_url}",
                    "--force-media-title={media_title}",
                    "--force-window=immediate",
                    *extra_args,
                ]

                super().__init__(
                    rpc_client=rpc_client,
                    player_path=player_path,
                    extra_args=extra_args
                )
        ```

        1. This is the important part, those arguments will later be passed to the player.
        There are two format fields you can use `{stream_url}` and `{media_title}`.

    Attributes:
        player_args_template: A list of arguments that are passed to the player command.
            Fields that are replaced are `{media_title}` and `{stream_url}`.
            This is only important if you are implementing your own player.

    """

    player_args_template: List[str]

    @abstractmethod
    def __init__(
        self,
        player_path: str,
        extra_args: List[str],
        play_callback: Optional[PlayCallback] = None,
    ):
        """__init__ for SubProcessPlayerBase

        Args:
            player_path: The path to the player's executable
            extra_args: Extra arguments to be passed to the player
            play_callback: Callback called upon starting to play a title with `play_title`
        """
        super().__init__(play_callback)

        self._sub_proc = None
        self._player_exec = player_path

    def play_title(self, anime: "Anime", stream: "ProviderStream"):
        subs = self._get_media_sub(stream, anime)
        arabic_sub = subs.get("Arabic")
        if not arabic_sub:
            arabic_sub = next((path for name, path in subs.items() if "ara" in name.lower()), None)
        chosen_sub = arabic_sub if arabic_sub else (next(iter(subs.values())) if subs else "")
        player_cmd = [
            i.format(
                media_title=self._get_media_title(anime, stream),
                stream_url=stream.url,
                subtitles=chosen_sub,
                referrer=stream.referrer,
                container=stream.container
            )
            for i in self.player_args_template
        ]
        player_cmd.insert(0, self._player_exec)
        if self._player_exec == "vlc":
            player_cmd.append("--sub-track=0")
        if isinstance(self._sub_proc, sp.Popen):
            self.kill_player()
        self._sub_proc = self._open_sproc(player_cmd)
        self._call_play_callback(anime, stream)

    def play_file(self, path: str):
        if isinstance(self._sub_proc, sp.Popen):
            self.kill_player()

        player_cmd = [self._player_exec, path]
        self._sub_proc = self._open_sproc(player_cmd)

    def wait(self):
        if self._sub_proc is not None:
            self._sub_proc.wait()

    def kill_player(self):
        if self._sub_proc is not None:
            self._sub_proc.kill()

    @staticmethod
    def _open_sproc(player_command: List[str]) -> sp.Popen:
        try:
            if os.name in ("nt", "dos"):
                sub_proc = sp.Popen(player_command)
            else:
                sub_proc = sp.Popen(
                    player_command, stdout=sp.DEVNULL, stderr=sp.DEVNULL
                )
        except FileNotFoundError:
            raise PlayerError(f"Executable {player_command[0]} was not found")

        return sub_proc
