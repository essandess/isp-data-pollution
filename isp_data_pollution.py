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


import argparse as ap, datetime as dt, numpy as np, numpy.random as npr, os, psutil, random, requests, signal, sys, tarfile, time
import urllib.request, urllib.robotparser as robotparser, urllib.parse as uprs
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from io import BytesIO
from faker import Factory

# headless Raspberry Pi
try:
    from pyvirtualdisplay import Display
    display = Display(visible=0, size=(1296,1018))
    display.start()
except ImportError:
    pass

# nice this process on UNIX
if hasattr(os,'nice'): os.nice(15)

gb_per_month = 50		# How many gigabytes to pollute per month
max_links_cached = 100000	# Maximum number of links to cache for download
max_links_per_page = 200	# Maximum number of links to add per page
max_links_per_domain = 400	# Maximum number of links to add per domain
search_url = 'http://www.google.com/search'	# keep unencrypted for ISP DPI
wordsite_url = 'http://svnweb.freebsd.org/csrg/share/dict/words?view=co&content-type=text/plain'
timeout = 20

blacklist_url = 'http://www.shallalist.de/Downloads/shallalist.tar.gz'
# Usage of the Shalla Blacklists:
# ===============================
#
# The Shalla Blacklists are property of Shalla Secure Services.
#
# This collection of url lists may be used for free for non
# commercial usage. This includes all kinds of private usage.
# The lists must not be given to any third party.

# tell my ISP that I use a really awful browser, along with random user agents (below)
user_agent = 'Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko'

# bias the content with non-random, diverse, link-heavy, popular content
seed_bias_links = ['http://my.xfinity.com/news',
                    'http://my.xfinity.com/entertainment',
                    'http://my.xfinity.com/shopping',
                    'http://www.cnbc.com/',
                    'https://news.google.com',
                    'https://news.yahoo.com',
                    'http://www.huffingtonpost.com',
                    'http://www.cnn.com',
                    'http://www.foxnews.com',
                    'http://www.nbcnews.com',
                    'http://www.usatoday.com',
                    'http://www.huffingtonpost.com',
                    'http://www.tmz.com',
                    'http://www.deadspin.com',
                    'http://www.dailycaller.com',
                    'http://www.sports.yahoo.com',
                    'http://www.espn.com',
                    'http://www.foxsports.com',
                    'http://www.finance.yahoo.com',
                    'http://www.money.msn.com',
                    'http://www.fool.com'
                    ]

# monkeypatch the read class method in RobotFileParser
# many sites will block access to robots.txt without a standard User-Agent header
class RobotFileParserUserAgent(robotparser.RobotFileParser):
    def read(self):
        """Reads the robots.txt URL and feeds it to the parser."""
        try:
            headers = {'User-Agent': user_agent, }
            request = urllib.request.Request(self.url, None, headers)
            f = urllib.request.urlopen(request)
            # f = urllib.request.urlopen(self.url)   #! original code
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                self.disallow_all = True
            elif err.code >= 400 and err.code < 500:
                self.allow_all = True
        else:
            raw = f.read()
            self.parse(raw.decode("utf-8").splitlines())

# Notes for the future:
# 1. The bandwidth usage is undoubtedly (much) smaller because gzip encoding is used
# 2. A lightweight proxy could be used for accurate bandwidth, and header editing

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
                 max_links_per_domain=max_links_per_domain,
                 user_agent=user_agent,
                 search_url=search_url,
                 blacklist_url=blacklist_url,
                 wordsite_url=wordsite_url,
                 seed_bias_links=seed_bias_links,
                 timeout=timeout,
                 quit_driver_every_call=False,
                 blacklist=True,verbose=True):
        self.max_links_cached = max_links_cached
        self.max_links_per_page = max_links_per_page
        self.max_links_per_domain = max_links_per_domain
        self.user_agent = user_agent
        self.search_url = search_url
        self.blacklist_url = blacklist_url
        self.wordsite_url = wordsite_url
        self.seed_bias_links = seed_bias_links
        self.blacklist = blacklist; self.verbose = verbose
        self.timeout = timeout
        self.quit_driver_every_call = quit_driver_every_call
        # self.gb_per_month = gb_per_month  # set in parseArgs
        # self.debug = debug  # set in parseArgs
        self.args = self.args = self.parseArgs()
        signal.signal(signal.SIGALRM, self.phantomjs_hang_handler) # register hang handler
        self.fake = Factory.create()
        self.hour_trigger = True
        self.twentyfour_hour_trigger = True
        self.links = set()
        self.link_count = dict()
        self.start_time = time.time()
        self.data_usage = 0
        self.get_blacklist()
        self.get_random_words()
        self.pollute_forever()

    def parseArgs(self):
        parser = ap.ArgumentParser()
        parser.add_argument('-bw', '--gb_per_month', help="GB per month", type=int, default=gb_per_month)
        parser.add_argument('-g', '--debug', help="Debug flag", action='store_true')
        args = parser.parse_args()
        for k in args.__dict__: setattr(self,k,getattr(args,k))
        self.sanity_check_arguments()
        return args

    def sanity_check_arguments(self):
        self.gb_per_month = min(2048,max(1,self.gb_per_month))  # min-max bandwidth limits

    def open_session(self):
        if not hasattr(self, 'session') or not isinstance(self.session,webdriver.phantomjs.webdriver.WebDriver):
            # phantomjs session
            # http://engineering.shapesecurity.com/2015/01/detecting-phantomjs-based-visitors.html
            # https://coderwall.com/p/9jgaeq/set-phantomjs-user-agent-string
            # http://phantomjs.org/api/webpage/property/settings.html
            # http://stackoverflow.com/questions/23390974/phantomjs-keeping-cache
            dcap = dict(DesiredCapabilities.PHANTOMJS)
            # dcap['browserName'] = 'Chrome'
            dcap['phantomjs.page.settings.userAgent'] = ( self.user_agent )
            dcap['phantomjs.page.settings.loadImages'] = ( 'false' )
            dcap['phantomjs.page.settings.clearMemoryCaches'] = ( 'true' )
            dcap['phantomjs.page.settings.resourceTimeout'] = ( max(2000,int(self.timeout * 1000)) )
            dcap['acceptSslCerts'] = ( True )
            dcap['applicationCacheEnabled'] = ( False )
            dcap['handlesAlerts'] = ( False )
            dcap['phantomjs.page.customHeaders'] = ( { 'Connection': 'keep-alive', 'Accept-Encoding': 'gzip, deflate, sdch' } )
            driver = webdriver.PhantomJS(desired_capabilities=dcap,service_args=['--disk-cache=false','--ignore-ssl-errors=false','--ssl-protocol=TLSv1.2'])
            driver.set_window_size(1296,1018)   # Tor browser size on Linux
            driver.implicitly_wait(self.timeout+10)
            driver.set_page_load_timeout(self.timeout+10)
            self.session = driver

    def quit_session(self):
        # http://stackoverflow.com/questions/25110624/how-to-properly-stop-phantomjs-execution
        if hasattr(self,'session'):
            self.session.close()
            self.session.service.process.send_signal(signal.SIGTERM)
            self.session.quit()
            del self.session

    def clear_session(self):
        # https://sqa.stackexchange.com/questions/10466/how-to-clear-localstorage-using-selenium-and-webdriver
        if hasattr(self, 'session'):
            self.session.delete_all_cookies()
            self.session.execute_script('window.localStorage.clear();')
            self.session.execute_script('window.sessionStorage.clear();')

    def get_blacklist(self):
        self.blacklist_domains = set()
        self.blacklist_urls = set()
        try:
            if self.blacklist:    # download the blacklist or not
                if self.verbose: print('Downloading the blacklist… ',end='',flush=True)
            else:
                raise Exception('Skip downloading the blacklist.')
            # http://stackoverflow.com/questions/18623842/read-contents-tarfile-into-python-seeking-backwards-is-not-allowed
            tgzstream = urllib.request.urlopen(urllib.request.Request(self.blacklist_url, headers={'User-Agent': self.user_agent}))
            tmpfile = BytesIO()
            while True:
                s = tgzstream.read(16384)
                if not s: break
                tmpfile.write(s)
            tgzstream.close()
            tmpfile.seek(0)
            tgz = tarfile.open(fileobj=tmpfile, mode='r:gz')
            # bash$ ls BL
            # COPYRIGHT	education	isp		recreation	updatesites
            # adv		finance		jobsearch	redirector	urlshortener
            # aggressive	fortunetelling	library		religion	violence
            # alcohol		forum		military	remotecontrol	warez
            # anonvpn		gamble		models		ringtones	weapons
            # automobile	global_usage	movies		science		webmail
            # chat		government	music		searchengines	webphone
            # costtraps	hacking		news		sex		webradio
            # dating		hobby		podcasts	shopping	webtv
            # downloads	homestyle	politics	socialnet
            # drugs		hospitals	porn		spyware
            # dynamic		imagehosting	radiotv		tracker
            for member in [ 'downloads', 'drugs', 'hacking', 'gamble', 'porn', 'spyware', 'updatesites', 'urlshortener', 'violence', 'warez', 'weapons' ]:
                self.blacklist_domains |= set(tgz.extractfile('BL/{}/domains'.format(member)).read().decode('utf-8').splitlines())
                self.blacklist_urls |= set(tgz.extractfile('BL/{}/urls'.format(member)).read().decode('utf-8').splitlines())
            tgz.close()
            tmpfile.close()
            if self.verbose: print('done.',flush=True)
        except BaseException as e:
            if self.verbose: print(e)
        # ignore problem urls
        self.blacklist_urls |= { 'about:blank' }

    def get_random_words(self):
        try:
            reqsession = requests.Session()
            reqsession.headers.update({'User-Agent': self.user_agent})
            response = reqsession.get(self.wordsite_url,timeout=10)
            self.words = response.content.decode('utf-8').splitlines()
            reqsession.close()
        except BaseException as e:
            if self.debug: print(e)
            self.words = [ 'FUBAR' ]
        # if self.debug: print('There are {:d} words.'.format(len(self.words)))

    def pollute_forever(self):
        self.open_session()
        self.seed_links()
        self.clear_session()
        if self.quit_driver_every_call: self.quit_session()
        while True: # pollute forever, pausing only to meet the bandwidth requirement
            try:
                if self.diurnal_cycle_test():
                    self.pollute()
                else:
                    time.sleep(self.chi2_mean_std(3.,1.))
                if npr.uniform() < 0.005: self.set_user_agent()  # reset the user agent occasionally
                self.elapsed_time = time.time() - self.start_time
                self.exceeded_bandwidth_tasks()
                self.every_hour_tasks()
                time.sleep(self.chi2_mean_std(0.5,0.2))
            except BaseException as e:
                if self.debug: print(e)

    def pollute(self):
        if not self.quit_driver_every_call: self.check_phantomjs_process()
        if len(self.links) < 2000:
            if self.quit_driver_every_call: self.open_session()
            self.seed_links()
            self.clear_session()
            if self.quit_driver_every_call: self.quit_session()
        url = self.remove_link()
        if self.quit_driver_every_call: self.open_session()
        self.get_url(url)
        self.clear_session()
        if self.quit_driver_every_call: self.quit_session()

    def seed_links(self):
        # bias with non-random seed links
        self.links |= set(self.seed_bias_links)
        if len(self.links) < self.max_links_cached:
            num_words = max(1,int(np.round(npr.poisson(1)+0.5)))  # mean of 1.5 words per search
            word = ' '.join(random.sample(self.words,num_words))
            if self.debug: print('Seeding with search for \'{}\'…'.format(word))
            # self.add_url_links(self.websearch(word).content.decode('utf-8'))
            self.get_websearch(word)

    def diurnal_cycle_test(self):
        now = dt.datetime.now()
        tmhr = now.hour + now.minute/60.
        phase = npr.normal(14.,1.)
        exponent = min(0.667,self.chi2_mean_std(0.333,0.1))
        def cospow(x,e):  # flattened cosine with e < 1
            c = np.cos(x)
            return np.sign(c) * np.power(np.abs(c), e)
        diurn = max(0.,0.5*(1.+cospow((tmhr-phase)*(2.*np.pi/24.),exponent)))
        flr = min(0.1,self.chi2_mean_std(0.02,0.002))
        val = flr + (1.-flr)*diurn
        return npr.uniform() < val

    def chi2_mean_std(self,mean=1.,std=0.1):
        '''
        Chi-squared random variable with given mean and standard deviation.
        '''
        scale = 2.*mean/std
        nu = mean*scale
        return npr.chisquare(nu)/scale

    def exceeded_bandwidth_tasks(self):
        if self.bandwidth_test():
            # decimate the stack and clear the cookies
            if len(self.links) > int(np.ceil(0.81*self.max_links_cached)):
                for url in random.sample(self.links,int(np.ceil(len(self.links)/10.))):
                    self.remove_link(url)
            time.sleep(120)

    def every_hour_tasks(self):
        if int(self.elapsed_time/60. % 60.) == 59:
            # reset user agent, clear out cookies
            if self.hour_trigger:
                self.set_user_agent()
                if hasattr(self,'session'):
                    # self.session.cookies.clear() # requests session
                    self.session.delete_all_cookies()
                self.hour_trigger = False
        else:
            self.hour_trigger = True
        self.every_day_tasks()
        self.every_two_weeks_tasks()

    def every_day_tasks(self):
        if int(self.elapsed_time/3600. % 24.) == 23:
            # clear out cookies every day, and seed more links
            if self.twentyfour_hour_trigger:
                if hasattr(self,'session'):
                    self.seed_links()
                    # restart the session
                    self.quit_session()
                    self.open_session()
                else:
                    self.open_session()
                    self.seed_links()
                    if self.quit_driver_every_call: self.quit_session()
                self.twentyfour_hour_trigger = False
        else:
            self.twentyfour_hour_trigger = True

    def every_two_weeks_tasks(self):
        if self.elapsed_time > 3600.*24*14:
            # reset bw stats and (really) decimate the stack every couple of weeks
            self.start_time = time.time()
            self.data_usage = 0
            if len(self.links) > int(np.ceil(0.49*self.max_links_cached)):
                for url in random.sample(self.links,int(np.ceil(len(self.links)/3.))):
                    self.remove_link(url)

    def set_user_agent(self):
        global user_agent
        self.user_agent = self.fake.user_agent() if npr.random() < 0.95 else user_agent
        self.session.capabilities.update({'phantomjs.page.settings.userAgent': self.user_agent})

    def remove_link(self):
        url = random.sample(self.links,1)[0]
        if npr.uniform() < 0.95:  # 95% 1 GET, ~5% 2 GETs, .2% three GETs
            self.links.remove(url)  # pop a random item from the stack
            self.decrement_link_count(url)
        return url

    def add_link(self,url):
        result = False
        domain = self.domain_name(url)
        self.link_count.setdefault(domain,0)
        if len(self.links) < self.max_links_cached \
                and self.link_count[domain] < self.max_links_per_domain \
                and url not in self.links:
            self.links.add(url)
            self.increment_link_count(url,domain)
            result = True
            # if self.debug: print('\tAdded link \'{}\'…'.format(url))
        return result

    def decrement_link_count(self,url,domain=None):
        if domain is None: domain = self.domain_name(url)
        self.link_count.setdefault(domain,0)
        if self.link_count[domain] > 0: self.link_count[domain] -= 1

    def increment_link_count(self,url,domain=None):
        if domain is None: domain = self.domain_name(url)
        self.link_count.setdefault(domain,0)
        self.link_count[domain] += 1

    def domain_name(self,url):
        return '.'.join(uprs.urlparse(url).netloc.split('.')[-2:])

    def get_websearch(self,query):
        '''HTTP GET of a websearch, then add any embedded links.'''
        url = uprs.urlunparse(uprs.urlparse(self.search_url)._replace(query='q={}&safe=active'.format(query)))
        # return self.session.get(url)
        signal.alarm(self.timeout+2)  # set an alarm
        try:
            self.session.get(url)  # selenium driver
        except self.TimeoutError as e:
            if self.debug: print(e)
        finally:
            signal.alarm(0)  # cancel the alarm
        self.data_usage += len(self.session.page_source)
        new_links = self.websearch_links()
        if len(self.links) < self.max_links_cached: self.add_url_links(new_links,url)

    def websearch_links(self):
        '''Webpage format for a popular search engine, <div class="g">'''
        try:
            return [ div.find_element_by_tag_name('a').get_attribute('href') \
                for div in self.session.find_elements_by_css_selector('div.g') \
                     if div.find_element_by_tag_name('a').get_attribute('href') is not None ]
        except BaseException as e:
            if self.debug: print(e)
            return []

    def get_url(self,url):
        '''HTTP GET of the url, and add any embedded links.'''
        if not self.check_robots(url): return  # bail out if robots.txt says to
        signal.alarm(self.timeout+2)  # set an alarm
        try:
            self.session.get(url)  # selenium driver
        except self.TimeoutError as e:
            if self.debug: print(e)
        finally:
            signal.alarm(0)  # cancel the alarm
        self.data_usage += len(self.session.page_source)
        new_links = self.url_links()
        if len(self.links) < self.max_links_cached: self.add_url_links(new_links,url)

    def url_links(self):
        '''Generic webpage link finder format.'''
        try:
            return [ a.get_attribute('href') \
                     for a in self.session.find_elements_by_tag_name('a') \
                     if a.get_attribute('href') is not None ]
        except BaseException as e:
            if self.debug: print(e)
            return []

    def check_robots(self,url):
        result = False
        try:
            url_robots = uprs.urlunparse(uprs.urlparse(url)._replace(scheme='https',path='/robots.txt',query='',params=''))
            rp = RobotFileParserUserAgent()
            rp.set_url(url_robots)
            rp.read()
            result = rp.can_fetch(self.user_agent,url)
        except BaseException as e:
            if self.debug: print(e)
        del rp      # ensure self.close() in urllib
        return result

    def add_url_links(self,links,url=''):
        k = 0
        for link in sorted(links,key=lambda k: random.random()):
            lp = uprs.urlparse(link)
            if (lp.scheme == 'http' or lp.scheme == 'https') and not self.blacklisted(link):
                if self.add_link(link): k += 1
                if k > self.max_links_per_page: break
        if self.verbose or self.debug:
            current_url = url  # default
            try:
                current_url = self.session.current_url
                # the current_url method breaks on a lot of sites, e.g.
                # python3 -c 'from selenium import webdriver; driver = webdriver.PhantomJS(); driver.get("https://github.com"); print(driver.title); print(driver.current_url); driver.quit()'
            except BaseException as e:
                if self.debug: print(e)
        if self.debug:
            print("'{}': {:d} links added, {:d} total".format(current_url,k,len(self.links)))
        elif self.verbose:
            self.print_progress(k,current_url)

    def print_progress(self,num_links,url,terminal_width=80):
        # truncate or fill with white space
        text_suffix = ': {:d} links added, {:d} total'.format(num_links,len(self.links))
        chars_used =  2 + len(text_suffix)
        if len(url) + chars_used > terminal_width:
            url = url[:terminal_width-chars_used-1] + '…'
        text = "'{}'{}".format(url,text_suffix)
        text = text[:min(terminal_width,len(text))] + ' ' * max(0,terminal_width-len(text))
        print(text,end='',flush=True)
        time.sleep(0.01)
        print('\r',end='',flush=True)

    def blacklisted(self,link):
        return link in self.blacklist_urls or self.domain_name(link) in self.blacklist_domains

    def bandwidth_test(self):
        running_bandwidth = self.data_usage/(self.elapsed_time+900.)
        running_bandwidth = running_bandwidth/407.	# Convert to GB/month, 2**30/(3600*24*30.5)
        # if self.debug: print('Using {} GB/month'.format(running_bandwidth))
        return running_bandwidth > self.gb_per_month

    # handle phantomjs timeouts
    class TimeoutError(Exception):
        pass

    def phantomjs_hang_handler(self, signum, frame):
        # https://github.com/detro/ghostdriver/issues/334
        # http://stackoverflow.com/questions/492519/timeout-on-a-function-call
        if self.debug: print('Looks like phantomjs has hung.')
        try:
            self.quit_session()
            self.open_session()
        except BaseException as e:
            if self.debug: print(e)
            raise self.TimeoutError('Unable to quit the session as well.')
        raise self.TimeoutError('phantomjs is taking too long')

    def check_phantomjs_process(self):
        '''Check if phantomjs is running.'''
        # Check rss and restart if too large, then check existence
        # http://stackoverflow.com/questions/568271/how-to-check-if-there-exists-a-process-with-a-given-pid-in-python
        try:
            if not hasattr(self,'session'): self.open_session()
            pid, rss_mb = self.phantomjs_pid_and_memory()
            if rss_mb > 1024:  # 1 GB rss limit
                self.quit_session()
                self.open_session()
                pid = self.phantomjs_pid()
            # check existence
            os.kill(pid, 0)
        except (OSError,BaseException) as e:
            if self.debug: print(e)
            return False
        except psutil.ZombieProcess as e:
            if self.debug: print(e)
            raise Exception("There's a phantomjs zombie, and the thread shouldn't have reached this statement.")
        else:
            return True

    def phantomjs_pid_and_memory(self):
        """ Return the pid and memory (MB) of the phantomjs process,
        restart if it's a zombie, and exit if a restart isn't working
        after three attempts. """
        for k in range(3):    # three strikes
            try:
                pid = self.session.service.process.pid
                rss_mb = psutil.Process(pid).memory_info().rss / float(2 ** 20)
            except (psutil.ZombieProcess,BaseException) as e:
                if self.debug: print(e)
                self.quit_session()
                self.open_session()
            finally:
                break
        else:  # throw in the towel and exit if no viable phantomjs process after multiple attempts
            sys.exit()
        return (pid, rss_mb)

if __name__ == "__main__":
    ISPDataPollution()
