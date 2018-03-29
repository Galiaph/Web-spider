import requests
from lxml import html
import time

def get_site_data(url):
    try:
        return requests.get(url).text
    except requests.HTTPError as identifier:
        print("error in http request: {}".format(identifier.args))
        return None


def get_parse_list(url, domen):
    count = 1
    parse_list = list()
    string = url[:url.find(domen)+len(domen)]
    while True:
        site_data = get_site_data(url)
        if not site_data:
            break
        tree = html.fromstring(site_data)
        node = tree.xpath('//div[@class="xf-product js-product "]/figure[@class="xf-product__picture xf-product-picture"]/a[@class="xf-product-picture__link"]/@href')
        if not node:
            break
        for x in node:
            parse_list.append(string + x)
        count += 1
        url = url[:url.find('=')+1] + str(count)
        break
    return parse_list


def main():
    get_list = get_parse_list("https://www.perekrestok.ru/promos/post?page=1", ".ru")
    for x in get_list:
        print(x)
    print(len(get_list))


if __name__ == "__main__":
    s = time.time()
    main()
    print("time spent: {:.2f}".format(time.time() - s))

