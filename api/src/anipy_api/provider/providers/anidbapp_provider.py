import base64
import json
import re
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import m3u8
from requests import Request

from anipy_api.provider import (BaseProvider, Episode, ProviderInfoResult,
                                ProviderSearchResult, ProviderStream)
from anipy_api.provider.base import ExternalSub, LanguageTypeEnum
from anipy_api.provider.filter import FilterCapabilities, Filters, Status

def _normalize_sub_lang(label: str, fallback: str) -> tuple:
    lbl = (label or "").lower()
    if "ara" in lbl or "arabic" in lbl:
        return ("Arabic", "ara")
    if "eng" in lbl or "english" in lbl:
        return ("English", "eng")
    if "ger" in lbl or "german" in lbl or "deutsch" in lbl:
        return ("German", "ger")
    if "spa" in lbl or "spanish" in lbl or "español" in lbl:
        if "latin" in lbl:
            return ("Spanish (Latin America)", "spa")
        return ("Spanish", "spa")
    if "fre" in lbl or "french" in lbl or "français" in lbl:
        return ("French", "fre")
    if "ita" in lbl or "italian" in lbl:
        return ("Italian", "ita")
    if "por" in lbl or "portuguese" in lbl:
        return ("Portuguese (Brazil)", "por")
    if "rus" in lbl or "russian" in lbl:
        return ("Russian", "rus")
    return (label or "Unknown", fallback or "und")
class AniDBAppProvider(BaseProvider):
    NAME: str = "anidbapp"
    BASE_URL: str = "https://hianime.at"
    FILTER_CAPS: FilterCapabilities = FilterCapabilities.NO_QUERY

    def get_info(self, identifier: str) -> ProviderInfoResult:
        return ProviderInfoResult(
            name=identifier,
            image=None,
            genres=[],
            status=Status.ONGOING,
            synopsis="",
            release_year=None,
            alternative_names=[],
        )

    def get_search(
        self, query: str, filters: Filters = Filters()
    ) -> List[ProviderSearchResult]:
        req = Request("GET", f"{self.BASE_URL}/search", params={"keyword": query})
        res = self._request_page(req)
        soup = BeautifulSoup(res.text, "html.parser")
        main_content = soup.find("div", id="main-content") or soup
        cards = main_content.find_all("div", class_="film-detail")
        results = []
        for c in cards:
            h3 = c.find("h3", class_="film-name")
            if h3 and h3.a:
                name = h3.a.get("title") or h3.a.text.strip()
                href = h3.a["href"]
                ident = href.rstrip("/").split("-")[-1]
                results.append(
                    ProviderSearchResult(
                        identifier=ident,
                        name=name,
                        languages={LanguageTypeEnum.SUB, LanguageTypeEnum.DUB},
                    )
                )
        return results

    def get_episodes(self, identifier: str, lang: LanguageTypeEnum) -> List[Episode]:
        req = Request("GET", f"{self.BASE_URL}/api/theme/episode/list/{identifier}")
        res = self._request_page(req).json()
        soup = BeautifulSoup(res.get("html", ""), "html.parser")
        episodes = [
            int(a["data-number"])
            for a in soup.find_all("a", class_="ep-item")
            if "data-number" in a.attrs
        ]
        return sorted(list(set(episodes)))

    def get_video(
        self, identifier: str, episode: Episode, lang: LanguageTypeEnum
    ) -> List[ProviderStream]:
        req = Request("GET", f"{self.BASE_URL}/api/theme/episode/list/{identifier}")
        res = self._request_page(req).json()
        soup = BeautifulSoup(res.get("html", ""), "html.parser")
        ep_item = soup.find("a", attrs={"data-number": str(episode)})
        if not ep_item:
            return []
        data_id = ep_item["data-id"]

        req = Request(
            "GET", f"{self.BASE_URL}/api/theme/episode/servers", params={"episodeId": data_id}
        )
        res = self._request_page(req).json()
        srv_soup = BeautifulSoup(res.get("html", ""), "html.parser")
        mode_str = "dub" if lang == LanguageTypeEnum.DUB else "sub"
        target_item = None
        for item in srv_soup.find_all("div", class_="server-item"):
            if item.get("data-type") == mode_str:
                raw_hash = item.get("data-hash", "")
                try:
                    dec = base64.b64decode(raw_hash).decode("utf-8", "ignore")
                    if "zokoanime" in dec:
                        target_item = item
                        break
                except Exception:
                    pass
                if not target_item:
                    target_item = item
        if not target_item:
            return []

        embed_url = base64.b64decode(target_item["data-hash"]).decode("utf-8")
        req_embed = Request("GET", embed_url)
        res_embed = self._request_page(req_embed)
        m = re.search(r'window\.__P\s*=\s*"([^"]+)"', res_embed.text)
        if not m:
            return []
        blob = m.group(1)
        key = b"otaku-embed-v1"
        raw = base64.b64decode(blob)
        deobf = bytes([b ^ key[i % len(key)] for i, b in enumerate(raw)])
        player_data = json.loads(deobf.decode("utf-8"))
        m3u8_url = player_data.get("src")
        if not m3u8_url:
            return []

        subs = {}
        for sub in player_data.get("subtitles", []):
            raw_label = sub.get("label", "en")
            clean_name, iso_code = _normalize_sub_lang(raw_label, sub.get("lang", "en"))
            subs[clean_name] = ExternalSub(
                url=sub.get("src"),
                shortcode=iso_code,
                codec="vtt",
                lang=clean_name,
            )

        req_m3u8 = Request("GET", m3u8_url, headers={"Referer": embed_url})
        res_m3u8 = self._request_page(req_m3u8)
        playlist = m3u8.M3U8(res_m3u8.text, base_uri=urljoin(m3u8_url, "."))
        streams = []
        if len(playlist.playlists) == 0:
            streams.append(
                ProviderStream(
                    url=m3u8_url,
                    resolution=1080,
                    episode=episode,
                    language=lang,
                    subtitle=subs,
                    referrer=embed_url,
                    container="hls",
                )
            )
        else:
            for p in playlist.playlists:
                streams.append(
                    ProviderStream(
                        url=urljoin(playlist.base_uri, p.uri),
                        resolution=p.stream_info.resolution[1]
                        if p.stream_info.resolution
                        else 1080,
                        episode=episode,
                        language=lang,
                        subtitle=subs,
                        referrer=embed_url,
                        container="hls",
                    )
                )
        streams.sort(key=lambda s: s.resolution)
        return streams
