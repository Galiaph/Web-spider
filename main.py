from base import MyWebSpider
import asyncio
from lxml import html

class Perekrestok(MyWebSpider):
    async def get_parsed_content(self, url):
        html_data = await self.get_html_from_url(url)
        data = []
        tree = html.fromstring(html_data)
        node = tree.xpath('//div[@class="xf-product js-product "]/'
                          'figure[@class="xf-product__picture xf-product-picture"]/'
                          'a[@class="xf-product-picture__link"]/@href')
        if node:
            for item in node:
                data.append(item)
        return data


def main():
    # get_list = get_parse_list("https://www.perekrestok.ru/promos/post?page=1", ".ru")
    # for x in get_list:
    #     print(x)
    # print(len(get_list))
    base_url = 'https://www.perekrestok.ru/'
    capture = '/catalog/'
    exclude = [':']  # нам не нужны ссылки, содержащие двоеточие;
    concurrency = 2  # рассчитываем на 20 работников;
    output = 'json'  # на выходе собираемся получить данные в файле csv;
    max_crawl = 10  # максимум ссылок помещаемых в очередь для сканирования;
    max_parse = 10  # максимум ссылок помещаемых в очередь для анализа;
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_5) "
                             "AppleWebKit 537.36 (KHTML, like Gecko) Chrome",
               "Accept": "text/html,application/xhtml+xml,"
                         "application/xml;q=0.9,image/webp,*/*;q=0.8"}
    web_crawler = Perekrestok(base_url, capture, concurrency, timeout=30,
                              verbose=True, output=output, headers=headers, exclude=exclude,
                              max_crawl=max_crawl, max_parse=max_parse, start_url="https://www.perekrestok.ru/promos/post?page=1")
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(web_crawler.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()

