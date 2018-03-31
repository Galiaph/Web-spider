import asyncio
import aiohttp
import time
import logging
import json
import csv
from collections import defaultdict
from urllib.parse import urljoin, urldefrag
from lxml import html

class MyQueue(asyncio.Queue):
    """ очередь с лимитом """

    def __init__(self, maxsize=0, capacity=0, *, loop=None):
        """
        :param maxsize: максимальное количество элементов в очереди, в одно и тоже время.
        :param capacity: максимальное количество входящих элементов,
            выше которого, очередь отказывается набирать задания.
        """

        super().__init__(maxsize, loop=None)
        if capacity is None:
            raise TypeError("Capacity can`t be None")
        if capacity < 0:
            raise ValueError("Capacity can`t be negative")

        self.capacity = capacity
        # счетчик входящих элементов
        self.put_counter = 0
        # показатель достижения счетчика максимума
        self.is_reached = False


    def put_nowait(self, item):
        if not self.is_reached:
            super().put_nowait(item)
            self.put_counter += 1
            if 0 < self.capacity == self.put_counter:
                self.is_reached = True


class MyWebSpider:
    """ Базовый класс веб-паука """

    OUTPUTS_FORMATS = ['json', 'csv', 'xls']

    def __init__(self, base_url, capture_pattern, concurency=2, timeout=300,
                 delay=0, headers=None, exclude=None, verbose=True, output='json', 
                 max_crawl=0, max_parse=0, start_url=None, retries=2):

        assert output in self.OUTPUTS_FORMATS, 'Unsupported output format'

        self.output = output
        self.base = base_url
        self.start_url = self.base if not start_url else start_url
        self.capture = capture_pattern
        self.exclude = exclude if isinstance(exclude, list) else []
        self.concurency = concurency
        self.timeout = timeout
        self.delay = delay
        self.retries = retries
        self.q_crawl = MyQueue(capacity=max_crawl)
        self.q_parse = MyQueue(capacity=max_parse)
        self.brief = defaultdict(set)
        self.data = []
        self.can_parse = False

        logging.basicConfig(level='INFO')
        self.log = logging.getLogger()

        if not verbose:
            self.log.disabled = True

        self.client = aiohttp.ClientSession(headers=headers)


    def get_parsed_content(self, url):
        """
        Данный метод нужно реализовать в наследуемом классе
        :param url: ссылка, документ которой, нужно проанализировать.
        :return: словарь с данными.
        Должен быть coroutine.
        """
        raise NotImplementedError

    
    def get_urls(self, document):
        urls = []
        urls_to_parse = []
        dom = html.fromstring(document)
        for href in dom.xpath('//a/@href'):
            if any(e in href for e in self.exclude):
                continue
            url = urljoin(self.base, urldefrag(href)[0])
            if url.startswith(self.base):
                if self.capture in url:
                    urls_to_parse.append(url)
                urls.append(url)
        return urls, urls_to_parse


    async def get_html_from_url(self, url):
        async with self.client.get(url) as response:
            if response.status != 200:
                self.log.error('BAD RESPONSE: {}, {}'.format(response.status, url))
                return
            return await response.text()

    
    async def get_links_from_url(self, url):
        document = await self.get_html_from_url(url)
        return self.get_urls(document)

    async def __wait(self, name):
        if self.delay > 0:
            self.log.info('{} waits for {} sec.'.format(name, self.delay))
            await asyncio.sleep(self.delay)


    async def crawl_url(self):
        current_url = await self.q_crawl.get()
        try:
            if current_url in self.brief['crawling']:
                return
            self.log.info('Crawling: {}'.format(current_url))
            self.brief['crawling'].add(current_url)
            urls, urls_to_parse = await self.get_links_from_url(current_url)
            self.brief['crawled'].add(current_url)

            for url in urls:
                if self.q_crawl.is_reached:
                    self.log.warning('Maximum crawl length has been reached')
                    break
                await self.q_crawl.put(url)

            for url in urls_to_parse:
                if self.q_parse.is_reached:
                    self.log.warning('Maximum parse length has been reached')
                    break
                    
                if url not in self.brief['parsing']:
                    await self.q_parse.put(url)
                    self.brief['parsing'].add(url)
                    self.log.info('Captured: {}'.format(url))

            if not self.can_parse and self.q_parse.qsize() > 0:
                self.can_parse = True
        finally:
            self.q_crawl.task_done()


    async def parse_url(self):
        url_to_parse = await self.q_parse.get()
        self.log.info('Parsing: {}'.format(url_to_parse))
        try:
            content = await self.get_parsed_content(url_to_parse)
            self.data.append(content)
        except Exception:
            self.log.error('An error has occurred during crawling', exc_info=True)
        finally:
            self.q_parse.task_done()


    async def crawler(self):
        while True:
            await self.crawl_url()
            await self.__wait('Crawler')
        return


    async def parse(self):
        retries = self.retries
        while True:
            if self.can_parse:
                await self.parse_url()
            elif retries > 0:
                await asyncio.sleep(0.5)
                retries -= 1
            else:
                break
            await self.__wait('Parser')
        return


    def _write_json(self, name):
        with open('{}-{}.json'.format(name, time.time()), 'w') as file:
            json.dump(self.data, file)


    def _write_csv(self, name):
        headers = self.data[0].keys()
        with open('{}-{}.csv'.format(name, time.time()), 'w') as csvfile:
            writer = csv.DictWriter(csvfile, headers)
            writer.writeheader()
            writer.writerows(self.data)


    async def run(self):
        start = time.time()
        print('Start working')
        await self.q_crawl.put(self.start_url)

        def task_completed(future):
            exc = future.exception()
            if exc:
                self.log.error('Worker has finished with error: {} '.format(exc), exc_info=True)

        tasks = []
        for _ in range(self.concurency):
            fut_crawl = asyncio.ensure_future(self.crawler())
            fut_crawl.add_done_callback(task_completed)
            tasks.append(fut_crawl)

            fut_parse = asyncio.ensure_future(self.parse())
            fut_parse.add_done_callback(task_completed)
            tasks.append(fut_parse)

        await asyncio.wait_for(self.q_crawl.join(), self.timeout)
        await self.q_parse.join()

        for task in tasks:
            task.cancel()

        await self.client.close()
        end = time.time()
        print('Done in {} seconds'.format(end - start))
        assert self.brief['crawling'] == self.brief['crawled'], 'Crawling and crawled urls do not match'

        assert len(self.brief['parsing']) == len(self.data), 'Parsing length does not equal parsed length'

        self.log.info('Total crawled: {}'.format(len(self.brief['crawled'])))
        self.log.info('Total parsed: {}'.format(len(self.data)))
        self.log.info('Starting write to file')

        name = self.base.split('//')[1].replace('www', '').replace('/', '')

        if self.output == 'json':
            self._write_json(name)
        elif self.output == 'csv':
            self._write_csv(name)

        print('Parsed data has been stored.')
        print('Task done!')

