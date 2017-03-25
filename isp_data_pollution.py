#!/usr/bin/env python3
#coding: utf-8
__author__ = 'stsmith'

# isp_data_pollution: bandwidth-limited ISP data pollution 

# Copyright 2017 Steven T. Smith <steve dot t dot smith at gmail dot com>, GPL

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import cgi, lxml.html, numpy as np, numpy.random as npr, os, random, requests, time, urllib.robotparser as robotparser, urllib.parse as uprs
from faker import Factory

# nice this process
os.nice(15)

gb_per_month = 50		# How many gigabytes to pollute per month
max_links_cached = 100000	# Maximum number of links to cache for download
max_links_per_page = 100	# Maximum number of links to add per page
search_url = 'http://startpage.com/do/search'	# Ensure no javascript, keep unencrypted for ISP DPI
word_site = 'http://svnweb.freebsd.org/csrg/share/dict/words?view=co&content-type=text/plain'

# tell my ISP that I use a really awful browser, along with random user agents (below)
user_agent = 'Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko'

class ISPDataPollution:
    '''Re: https://www.eff.org/deeplinks/2017/03/senate-puts-isp-profits-over-your-privacy
 
I pay my ISP a lot for data usage every month. I typically don't use
all the bandwidth that I pay for.  If my ISP is going to sell my
private browsing habits, then I'm going to pollute my browsing with
noise and use all the bandwidth that I pay for. This method
accomplishes this.

If everyone uses all the data they've paid for to pollute their
browsing history, then perhaps ISPs will reconsider the business model
of selling customer's private browsing history.

The alternative of using a VPN or Tor merely pushes the issue onto to
the choice of VPN provider, complicates networking, and adds the
real issue of navigating captchas when appearing as a Tor exit node.

The crawler uses the Python requests and lxml.html libraries, is hardcoded
to download html without javascript processing, will not download
images, and respects robots.txt, which all provide good security.
'''

    def __init__(self,gb_per_month=gb_per_month,
                 max_links_cached=max_links_cached,
                 max_links_per_page=max_links_per_page,
                 user_agent=user_agent,
                 search_url=search_url,
                 word_site=word_site,
                 debug=False):
        self.gb_per_month = gb_per_month
        self.max_links_cached = max_links_cached
        self.max_links_per_page = max_links_per_page
        self.user_agent = user_agent
        self.search_url = search_url
        self.word_site = word_site
        self.debug = debug
        self.fake = Factory.create()
        self.rp = robotparser.RobotFileParser()
        self.clear_cookies_trigger = True
        self.links = set()
        self.start_time = time.time()
        self.data_usage = 0
        self.open_session()
        self.get_random_words()
        self.pollute_forever()

    def get_random_words(self):
        try:
            response = self.session.get(self.word_site,timeout=10)
            self.words = response.content.decode('utf-8').splitlines()
        except BaseException as e:
            print(e)
            self.words = [ 'FUBAR' ]
        # if self.debug: print('There are {:d} words.'.format(len(self.words)))

    def pollute_forever(self):
        while True: # pollute forever, pausing only to meet the bandwidth requirement
            try:
                self.pollute()
                self.elapsed_time = time.time() - self.start_time
                self.exceeded_bandwidth_tasks()
                self.every_day_tasks()
                self.every_two_weeks_tasks()                
            except BaseException as e:
                print(e)

    def pollute(self):
        self.set_user_agent()
        if len(self.links) < self.max_links_cached:
            word = random.choice(self.words)
            # if self.debug: print('Word \'{}\'...'.format(word))
            self.add_search_links(self.websearch(word).content.decode('utf-8'))
        # if self.debug: print('There are {:d} links.'.format(len(self.links)))
        url = random.sample(self.links,1)[0];
        self.links.remove(url)	# pop a random item from the stack
        if self.debug: print(url)
        self.get_url(url)

    def exceeded_bandwidth_tasks(self):
        if self.bandwidth_test():
            # decimate the stack and clear the cookies
            if len(self.links) > int(np.ceil(0.81*self.max_links_cached)):
                self.links.difference_update(random.sample(self.links,int(np.ceil(len(self.links)/10.))))
            time.sleep(120)

    def every_day_tasks(self):
        if int(self.elapsed_time/3600. % 24.) == 23:
            # clear out cookies every day
            if self.clear_cookies_trigger:
                self.session.cookies.clear()
                self.clear_cookies_trigger = False
        else:
            self.clear_cookies_trigger = True

    def every_two_weeks_tasks(self):
        if self.elapsed_time > 3600.*24*14:
            # reset bw stats and (really) decimate the stack every couple of weeks
            self.start_time = time.time()
            self.data_usage = 0
            if len(self.links) > int(np.ceil(0.49*self.max_links_cached)):
                self.links.difference_update(random.sample(self.links,int(np.ceil(len(self.links)/3.))))
            # restart the session
            del self.session
            self.open_session()

    def open_session(self):
        if not hasattr(self,'session') or not isinstance(self.session,requests.sessions.Session):
            self.session = requests.Session()
            self.session.headers.update( {'User-Agent': self.user_agent} )
        
    def set_user_agent(self):
        global user_agent
        self.user_agent = self.fake.user_agent() if npr.random() < 0.95 else user_agent
        self.session.headers.update( {'User-Agent': self.user_agent} )

    def websearch(self,query):
        url = uprs.urlunparse(uprs.urlparse(self.search_url)._replace(query=query))
        return self.session.get(url)

    def get_url(self,url):
        '''HTTP GET of the url, and add any embedded links.'''
        if self.check_size_and_set_mimetype(url) and self.mimetype == 'text/html':
            self.data_usage += self.content_length
            try:
                if self.check_robots(url): response = self.session.get(url,allow_redirects=True,timeout=10)
            except BaseException as e:
                print(e)
            if len(self.links) < self.max_links_cached: self.add_url_links(response.content.decode('utf-8'))

    def check_size_and_set_mimetype(self,url,maximum=1048576):
        '''Return True if not too large, set the mimetype as well.'''
        self.mimetype = None
        self.mimetype_options = None
        self.content_length = 0
        try:
            resp = self.session.head(url,allow_redirects=True,timeout=10)
            resp.raise_for_status()
            if 'Content-Type' in resp.headers:
                self.mimetype, self.mimetype_options = cgi.parse_header(resp.headers['Content-Type'])
            if 'Content-Length' in resp.headers:
                self.content_length = int(resp.headers['Content-Length'])
                if self.content_length > maximum:
                    raise Exception('Warning: Content size {:d} too large at url \'{}\'.'.format(int(resp.headers['Content-Length']),url))
        except BaseException as e:
            print(e)
            return False
        return True

    def check_robots(self,url):
        url_robots = uprs.urlunparse(uprs.urlparse(url)._replace(path='/robots.txt',query='',params=''))
        self.rp.set_url(url_robots)
        self.rp.read()
        return self.rp.can_fetch('*',url)

    def add_search_links(self,doc):
        html = lxml.html.document_fromstring(doc)
        k = 0
        for element, attribute, link, pos in html.iterlinks():
            if attribute == 'href':
                upn = '.'.join(uprs.urlparse(link).netloc.split('.')[-2:])
                if not ( upn == 'startpage.com' or upn == 'startmail.com' or upn == 'ixquick-proxy.com' ):  # startpage-specific
                    ups = uprs.urlparse(link).scheme
                    if ups == 'http' or ups == 'https':
                        self.links.add(link)
                        k += 1
                        if k > self.max_links_per_page: break

    def add_url_links(self,doc):
        html = lxml.html.document_fromstring(doc)
        k = 0
        for element, attribute, link, pos in html.iterlinks():
            if attribute == 'href':
                ups = uprs.urlparse(link).scheme
                if (ups == 'http' or ups == 'https') and len(self.links) < self.max_links_cached:
                    self.links.add(link)
                    k += 1
                    if k > self.max_links_per_page: break

    def bandwidth_test(self):
        running_bandwidth = self.data_usage/(self.elapsed_time+900.)
        running_bandwidth = running_bandwidth/407.	# Convert to GB/month, 2**30/(3600*24*30.5)
        # if self.debug: print('Using {} GB/month'.format(running_bandwidth))
        return running_bandwidth > self.gb_per_month

if __name__ == "__main__":
    ISPDataPollution(debug=True)
