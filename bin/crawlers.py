from reviews import Review
import random
import time
import re
import sys
from bs4 import BeautifulSoup as bs
import page_property
import sqlite3

class ParentCrawler(object):
    def __init__(self, driver):
        self.driver = driver
        self.pagetype = 'parent_page'
        self.base_url = None
        self.url = None
        self.bookmarker = None
        self.attrs = {}
        self.restart = False

    def update_bookmarker(self, new_pos_dict):
        self.bookmarker.update(new_pos_dict)

    def update_attr(self, new_attrs):
        self.attrs.update(new_attrs)
    
    def init_child(self):
        self.review_crawler = ReviewCrawler(self.driver)
        self.review_crawler.base_url = self.base_url
        self.review_crawler.review_list = self.review_list
        self.review_crawler.bookmarker = self.bookmarker

    def init_group_crawler(self):
        self.group_crawler = ParentCrawler(self.driver) 
        self.group_crawler.base_url = self.base_url
        self.group_crawler.bookmarker = self.bookmarker

    def get_url_list(self, soup):
        tags = soup.findAll('div',{'class':'element_wrap'})
        div_list = []
        for x in tags:
            if x.find('div',{'class':'wrap al_border attraction_type_group'}):
                category = 'group'
            elif x.find('div',{'class':'wrap al_border attraction_element'}):
                category = 'review'
            else:
                raise TypeError('Neither group or review')

            try:
                num_reviews = x.find('div',{'class':'rs rating'}).a.text
                num_reviews = re.search('\d+', num_reviews).group().strip()
                num_reviews = int(num_reviews)
            except AttributeError:
                num_reviews = 0

            subtag = x.find('div',{'class':'property_title'})
            location = re.sub('\(\d+\)','', subtag.a.text).strip()
            url = self.base_url + subtag.a['href']
            div_list.append( {'category':category, 
                  'item':location, 
                  'num_reviews':num_reviews, 
                  'url':url} )
        return div_list

    def get_bookmark_url(self):
        bookmark_review_page = self.bookmarker.bookmarks.get('review_page', None)     
        bookmark_group_page = self.bookmarker.bookmarks.get('group_page', None)
        lookup_url = ''
        if self.pagetype == 'group_page':
            self.restart = False
            lookup_url = bookmark_review_page
        elif self.pagetype == 'parent_page':
            if bookmark_group_page:
                lookup_url = bookmark_group_page
            elif bookmark_review_page:
                self.restart = False
                lookup_url = bookmark_review_page
        return lookup_url


    def get_trunc_list(self, div_list):
        # this function returns a truncated list based on the bookmarks
        if self.restart == False:
            return div_list

        bookmark_url = self.get_bookmark_url()

        if not bookmark_url:
            return div_list

        url = [item['url'] for item in div_list if 'url' in item]

        link = re.sub('-o\w\d+', '', bookmark_url)                
        link = re.sub('#REVIEWS', '', link)                
        #will throw a value error if link not in url
        idx = url.index(link) if link in url else 0
        div_list = div_list[idx:]
        div_list[0]['url'] = bookmark_url
        return div_list
    
    def execfct(self, item):
        self.review_crawler.url = item['url']
        self.review_crawler.update_attr(self.attrs)
        self.review_crawler.update_attr({'name':item['item']})
        self.review_crawler.first = True
        self.review_crawler.start()

    def get_next_url(self, soup):
        tags = soup.find('div',{'id':'pager_top', 'class':'pgLinks'})
        try:
            next_url = tags.find(lambda tag: tag.name=='a' and tag.text == u"\u00BB")['href']
            return self.base_url + next_url
        except (TypeError, AttributeError):
            return None

    def clean_url(self, url):
        link = re.sub('-or\d+', '', url)                
        return re.sub('#REVIEWS', '', link)                

    def check_duplicate(self, div_props):
        # i need url, number of reviews
        with sqlite3.connect(self.review_list.dbname) as conn:
            cur = conn.cursor()
            qry = """SELECT count(*), url FROM reviews 
                    where url = {}
                    GROUP BY url
                    """.format('?')
            url = self.clean_url(div_props['url'])
            cur.execute(qry, [url])
            result = cur.fetchall()
            print "-"*20+"RESULT"+"-"*20
            print result
            print div_props

        print '\n'

        if div_props['num_reviews'] == 0:
            print "no reviews"
            return True, div_props

        if result and result[0][0] >= div_props['num_reviews']-10:
            print 'duplicate', div_props['item']
            return True, div_props

        try:
            num = result[0][0]-10
            num = {True: 0, False: num}[num <= 10] /10 * 10
            if num > 0:
                repstr = '-Reviews-or' + str(num)
                div_props['url'] = re.sub('-Reviews',repstr, div_props['url'])
        except IndexError:
            pass

        print 'exec', div_props['item']
        return False, div_props



    def start(self):
        while self.url: 
            self.update_bookmarker( {self.pagetype:self.url} )
            self.driver.get(self.url)
            time.sleep(2 + random.random() * 1)            
            html = self.driver.page_source
            soup = bs(html)

            #split get_url_list into two
            div_list = self.get_url_list(soup)       
            div_list = self.get_trunc_list(div_list)
            
            for item in div_list:
                if item['category'] == 'review':
                    #check if already in sql
                    duplicate = self.check_duplicate(item)
                    if duplicate[0]:
                        continue
                    self.execfct(duplicate[1])
                elif item['category'] == 'group':
#                    continue
                    self.url = item['url']
                    self.pagetype = 'group_page'
                    self.update_attr( {'parent_group': item['item']} )
                    self.start()
                    self.pagetype = 'parent_page'
                    self.update_attr( {'parent_group': ''} )
                    self.update_bookmarker({'group_page':''})

            self.url = self.get_next_url(soup)

         
class ReviewCrawler(object):
    # Parent sees child and sends review crawler
    def __init__(self, driver):
        self.pagetype = 'review_page'
        self.driver = driver
        self.base_url = None
        self.start_url = None
        self.url = None
        self.bookmarker = None
        self.review_list = None
        self.attrs = {}
        self.first = True
        self.sleep = False

        random.seed(208)

    def update_attr(self, new_attrs):
        self.attrs.update(new_attrs)

    def update_bookmarker(self, new_pos_dict):
        self.bookmarker.update(new_pos_dict)

    def get_url_list(self, soup):
        try:        
            tags = soup.find('div',{'id':'REVIEWS'}).findChildren(recursive=False)
            reviews = filter(lambda tag: tag.has_attr('id') and 'review_' in tag['id'], tags)
        except AttributeError:
            reviews = []
        return reviews

    def process_page(self):
        #trigger popup
        element = self.driver.find_elements_by_xpath("//span[@class='partnerRvw']/child::span")    
        try:
            element[0].click()
        except:
            pass
        time.sleep(random.randint(3,5))

        #Close the popup
        html = self.driver.page_source
        soup = bs(html)
        p = soup.find('div',{'class':'xCloseGreen'})
        if p:
            element = self.driver.find_element_by_xpath("//div[@class='xCloseGreen']")    
            element.click()

        #Resume expanding reviews
        element = self.driver.find_elements_by_xpath("//span[@class='partnerRvw']/child::span")    
        for x in element:
            try:
                x.click()
            except:
                pass
        
    def get_next_url(self, soup):
        navbar = soup.find('div',{'class': "unified pagination "})
        try:
            return self.base_url + navbar.find(lambda tag: tag.text == 'Next')['href']
        except:
            return None
        
    def execfct(self, review_soup):        
        review = Review(review_soup, self.attrs)
        self.review_list.append(review)

    def clean_url(self, url):
        link = re.sub('-or\d+', '', url)                
        return re.sub('#REVIEWS', '', link)                


    def start(self):
        avgs = [0,1]
        while self.url: 
            start = time.time()

            self.update_bookmarker({self.pagetype:self.url})
            self.driver.get(self.url)
            self.process_page()
            html = self.driver.page_source
            soup = bs(html)

            if self.first == True:
                self.first = False
                first_page = page_property.ReviewPage(soup, self.attrs, self.review_list.dbname, self.clean_url(self.url))
                first_page.DBdump()
                self.attrs['url'] = self.url

            div_list = self.get_url_list(soup)            
            for item in div_list:
                if random.random() < 0.005 and self.sleep == True:
                    num = random.randint(120, 180)
                    print 'sleeping for ', num
                    time.sleep(num)
                    print 'started again'
                self.execfct(item)

            elapsed = time.time() - start
        
            avgs[0] = elapsed/avgs[1] + avgs[0] * (1 - 1./avgs[1])
            avgs[1] += 1
            sys.stdout.flush()
            sys.stdout.write("\r average time/page: % f" % avgs[0])
            self.url = self.get_next_url(soup)
            if not self.url:
                time.sleep(2)
                self.url = self.get_next_url(soup)

            
