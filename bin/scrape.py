from crawlers import ParentCrawler
from selenium import webdriver
from bookmark import Bookmark
from reviews import ReviewList

#["Siem Reap", "/Attractions-g297390-Activities-Siem_Reap_Siem_Reap_Province.html"], 

import json

with open('old/cities_laos.json', 'r') as f:
    lines = f.read()
city_data = json.loads(lines)


base_url = "http://www.tripadvisor.com"
profile = webdriver.FirefoxProfile("/Users/alexrhee/Library/Application Support/Firefox/Profiles/Selenium")
driver = webdriver.Firefox(profile)
driver.set_page_load_timeout(15)
crawler = ParentCrawler(driver)

scrape_bookmark = Bookmark('bookmark.json')
crawler.restart = True
crawler.base_url = base_url
crawler.update_attr( {'country':'Laos', 'type':'Things to do'} )
crawler.review_list = ReviewList('laos.db','reviews')
crawler.bookmarker = scrape_bookmark
crawler.init_child()

if crawler.restart == True:
	city_name, city_url = zip(*city_data)
	city = scrape_bookmark.bookmarks.get('city', None)
	idx = city_name.index(city) if city in city_name else -1
	city_data = city_data[idx+1:]
	if scrape_bookmark.bookmarks.get('parent_page', None):
		city_data[0] = (city_data[0][0],scrape_bookmark.bookmarks['parent_page'].replace(base_url,''))

for city in city_data:		
    crawler.url = base_url + city[1]
    crawler.update_attr({'location':city[0]})
    crawler.start()
    scrape_bookmark.bookmarks['city'] = city[0]
