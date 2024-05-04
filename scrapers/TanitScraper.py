import asyncio
import re
from unicodedata import normalize
import aiohttp
import bs4
import json
import math

from aiohttp import ClientSession, ServerTimeoutError, ClientResponse
from tenacity import retry, retry_if_exception_type
from scrapers.BaseScraper import BaseScraper


class TanitScraper(BaseScraper):
    def __init__(self, config):
        super().__init__(config)

    async def fetch_last_listings_page(self) -> int:
        """Fetches the number of the last page of job listings."""

        async with self._session.get(self._config.BASE_URL + "1") as response:
            print(self._config.BASE_URL + "1")
            self.check_timeout(response)
            soup = bs4.BeautifulSoup(await response.text(), 'lxml',
                                     parse_only=bs4.SoupStrainer(name="div", attrs={"id": "list_nav"}))

            last_page_link = soup.select_one(self._config.last_page_item)
            last_page = re.search(r'page=(\d+)', last_page_link['href']).group(1)

            assert last_page.isdigit(), f"The string '{last_page}' cannot be converted to an integer"
            return int(last_page)

    @retry(retry=retry_if_exception_type(ServerTimeoutError))
    async def fetch_job_postings(self, url: str):
        async with self._session.get(url) as response:
            self.check_timeout(response)
            soup = bs4.BeautifulSoup(await response.text(), 'lxml',
                                     parse_only=bs4.SoupStrainer(name=self._config.job_listing_item))
            for listing in soup.find_all(self._config.job_listing_item):
                """I opted to add dictionaries continaing job title, zone and posting date in _postings here."""
                job_info = {
                    "Title": f"{listing.select_one(self._config.title).string.strip()}",
                    "Employer": f'{listing.select_one(self._config.employer).string.strip()}',
                    "Zone": f"{listing.select_one(self._config.zone).string.strip()}",
                    "posting_date": f"{listing.select_one(self._config.posting_date).string.strip()}",
                    "url": f'{listing.find("a")["href"]}'
                }
                print(job_info)
                self._postings.put_nowait(job_info)

    @retry(retry=(retry_if_exception_type(AttributeError) | retry_if_exception_type(
        aiohttp.ClientConnectorError) | retry_if_exception_type(ServerTimeoutError) | retry_if_exception_type(
        aiohttp.ServerDisconnectedError)))
    async def parse_job_posting(self, url: str):
        async with self._session.get(url) as response:
            self.check_timeout(response)
            soup = bs4.BeautifulSoup(await response.text(), "lxml", parse_only=bs4.SoupStrainer('div')).select_one(
                'div.detail-offre')
            job_details_item = soup.select_one('div.infos_job_details')
            job_listing = {
                "Postes vacants": None,
                "Niveau d'étude": None,
                "Type d'emploi désiré": None,
                "Rémunération proposée": None,
                "Langue": None,
                "Experience": None,
                "Genre": None,
            }
            for item in job_details_item.find_all('div', class_="col-md-4"):
                detail_title = str(item.find('dt').string.strip())
                detail_content = item.find('dd').string.strip()
                job_listing[detail_title[:detail_title.find(':')].strip()] = detail_content

            for title, content in zip(soup.find_all('h3'), soup.select('div.details-body__content.content-text')):
                job_listing[title.string.strip()] = normalize("NFKD", content.get_text(strip=True, separator=""))
            print(job_listing)
            return job_listing
