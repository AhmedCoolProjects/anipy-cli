import atexit
import hashlib
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

def _cached_arabic_subs(safe_name: str, ep: int) -> List[str]:
    """Return all previously fetched Arabic subtitle files for an episode,
    ordered by preference (best first)."""
    prefix = f'{safe_name}_EP{ep}.ara.'
    files = []
    try:
        for existing in os.listdir(SUB_DIR):
            if not existing.startswith(prefix):
                continue
            m = re.match(rf'^{re.escape(prefix)}(\d+)_[^.]+\.(?:srt|ass|vtt)$', existing, re.I)
            if m:
                files.append((int(m.group(1)), os.path.join(SUB_DIR, existing)))
    except Exception:
        pass
    files.sort()
    return [path for _, path in files]


SEASON_WORDS = {1: 'first-season', 2: 'second-season', 3: 'third-season',
                4: 'fourth-season', 5: 'fifth-season'}

def _season_word(title: str) -> str:
    m = re.search(r'\bseason\s*(\d+)', title, re.I)
    if m:
        return SEASON_WORDS.get(int(m.group(1)), f'{m.group(1)}st-season')
    return ''


def _score_subdl_row(clean_t: str, ep: int) -> int:
    """Score a subdl row for a given episode.

    Positive scores indicate the row contains this episode's subtitles.
    Rows that encode a full-season pack covering the episode are kept as
    fallback options with a low score.
    """
    eps = set()
    for m in re.finditer(r'\b(?:E|EP|Episode)\s*0*(\d{1,2})\b|[-–~]\s*0*(\d{1,2})\b', clean_t, re.I):
        g = m.group(1) or m.group(2)
        if g:
            eps.add(int(g))
    if len(eps) > 1:
        # Multi-episode row (pack). Usable but a fallback, only if it covers ep.
        return 1 if ep in eps else 0
    score = 0
    if re.search(rf'\b(?:EP?|S0?\dE)0?{ep}(?!\w|[-–~])', clean_t, re.I):
        score += 3
    if re.search(rf'-\s*0?{ep}(?!\w|[-–~])', clean_t):
        score += 2
    if re.search(rf'\bEpisode\s*0?{ep}(?!\w|[-–~])', clean_t, re.I):
        score += 2
    return score


def _slug_from_row(clean_t: str, fallback: str) -> str:
    m = re.search(r'\(([^()]+)\)', clean_t)
    if m:
        slug = m.group(1)
    else:
        m = re.search(r'\[([^\[\]]+)\]', clean_t)
        slug = m.group(1) if m else fallback
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', slug).strip('-').lower()[:24]
    return slug or fallback


def _pick_sub_from_zip(z: "zipfile.ZipFile", ep: int) -> Optional[str]:
    cands = []
    for n in z.namelist():
        ext = n.rsplit('.', 1)[-1].lower()
        if ext not in ('srt', 'ass', 'vtt'):
            continue
        base = os.path.basename(n).lower()
        sc = 0
        if re.search(rf'\bs0?\d\s*e\s*0?{ep}\b', base):
            sc += 4
        if re.search(rf'\b(?:ep?|episode)[.\s_-]*0?{ep}(?!\d)', base):
            sc += 3
        if re.search(rf'[-_.\s]0?{ep}\b(?!\d)', base):
            sc += 2
        cands.append((sc, {'ass': 1, 'vtt': 0, 'srt': 0}[ext], n))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
    best = cands[0]
    if best[0] > 0:
        return best[2]
    # No episode info in any filename: only trust a single-subtitle zip
    return best[2] if len(cands) == 1 else None


def _looks_arabic(data: bytes) -> bool:
    try:
        text = data.decode('utf-8', 'ignore')
    except Exception:
        return False
    return sum(1 for ch in text[:20000] if '\u0600' <= ch <= '\u06ff') >= 10


def fetch_arabic_subtitles(title: str, ep: int, alt_titles=None) -> List[str]:
    """Fetch multiple Arabic subtitle files for an episode from SubDL.

    Returns a list of cached file paths, ordered by preference (best first).
    Every entry points to the exact requested episode, extracted from
    single-episode downloads or full-season packs, and verified to contain
    Arabic text.
    """
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', title)[:30]
    cached = _cached_arabic_subs(safe_name, ep)
    if cached:
        return cached

    queries = [title]
    if alt_titles:
        queries.extend(alt_titles)

    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 'Referer': 'https://subdl.com/'}

    rows = []
    seen_hrefs = set()
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
            except Exception:
                continue
            for res in results[:3]:
                link = res.get('link')
                if not link:
                    continue
                season_word = _season_word(raw_title)
                sub_paths = [f'{link}/{season_word}/arabic'] if season_word else []
                sub_paths += [f'{link}/arabic', link]
                for sub_path in sub_paths:
                    try:
                        r_page = requests.get(f'https://subdl.com{sub_path}', headers=headers, timeout=4)
                        if r_page.status_code != 200:
                            continue
                        soup = BeautifulSoup(r_page.text, 'html.parser')
                        for a in soup.find_all('a', href=lambda h: h and 'dl.subdl.com' in h):
                            href = a['href']
                            if href in seen_hrefs:
                                continue
                            # Walk up; keep the text of the tightest node that
                            # still holds exactly one download link, so list-style
                            # pages give per-episode rows instead of the whole pack
                            # container.
                            node = a.parent
                            row_text = ' '.join(a.text.split())
                            tight_text = row_text
                            while node is not None:
                                dl_links = node.find_all('a', href=lambda h: h and 'dl.subdl.com' in h)
                                if len(dl_links) > 1:
                                    break
                                row_text = ' '.join(node.text.split())
                                if len(re.findall(r'\bE\d{1,2}\b', row_text, re.I)) == 1:
                                    tight_text = row_text
                                node = node.parent
                            if not re.search(r'\b(?:E|EP|Episode)\s*\d{1,2}\b', tight_text, re.I):
                                tight_text = row_text
                            clean_t = tight_text
                            score = _score_subdl_row(clean_t, ep)
                            if score <= 0:
                                continue
                            seen_hrefs.add(href)
                            is_cr = 'crunchyroll' in clean_t.lower()
                            rows.append((score, is_cr, href, clean_t))
                    except Exception:
                        continue
    if not rows:
        return []

    rows.sort(key=lambda c: (c[0], c[1]), reverse=True)
    found = []
    used_slugs = set()
    seen_hashes = set()
    for score, is_cr, href, clean_t in rows[:8]:
        slug = _slug_from_row(clean_t, f'ar{len(found) + 1}')
        if slug in used_slugs:
            slug = f'{slug}-{len(found) + 1}'
        used_slugs.add(slug)
        try:
            r_zip = requests.get(href, headers=headers, timeout=8)
            z = zipfile.ZipFile(io.BytesIO(r_zip.content))
            picked = _pick_sub_from_zip(z, ep)
            if not picked:
                continue
            data = z.read(picked)
            if not _looks_arabic(data):
                continue
            content_hash = hashlib.md5(data).hexdigest()
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)
            ext = picked.rsplit('.', 1)[-1].lower()
            rank = len(found)
            out_path = os.path.join(SUB_DIR, f'{safe_name}_EP{ep}.ara.{rank}_{slug}.{ext}')
            with open(out_path, 'wb') as f:
                f.write(data)
            found.append(out_path)
        except Exception:
            continue
    return found

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

        # Fetch multiple Arabic subtitle options (best first) so the user is
        # not stuck with a single (possibly wrong) track.
        arabic_subs = {}
        if anime and getattr(anime, "name", None):
            alts = getattr(anime, "alternative_names", None)
            for path in fetch_arabic_subtitles(anime.name, stream.episode, alts):
                key = "Arabic"
                m = re.search(r'\.ara\.\d+_([^.]+)(?:\.\d+)?\.', os.path.basename(path))
                if m:
                    key = f"Arabic ({m.group(1)})"
                arabic_subs[key] = path

        # Arabic tracks go first so the best one is selected by default,
        # with the rest available for switching in the player.
        return {**arabic_subs, **subtitles}

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
        sub_files = list(subs.values())
        subtitles = ",".join(sub_files)
        preferred_sub = sub_files[0] if sub_files else ""
        player_cmd = [
            i.format(
                media_title=self._get_media_title(anime, stream),
                stream_url=stream.url,
                subtitles=subtitles,
                preferred_sub=preferred_sub,
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
