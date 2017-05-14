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

__version__ = '1.1'

import argparse as ap, datetime as dt, numpy as np, numpy.random as npr, os, psutil, random, requests, signal, sys, tarfile, time
import urllib.request, urllib.robotparser as robotparser, urllib.parse as uprs
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import WebDriverWait
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
short_timeout = 3
phantomjs_rss_limit_mb = 1024  # Default maximum meory limit of phantomjs processs (MB)
terminal_width = 80  # tty width, standard is 80 chars; add code to adapt later

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

    timeout = short_timeout  # short-term timeout

    def read(self):
        """Reads the robots.txt URL and feeds it to the parser."""
        try:
            headers = {'User-Agent': user_agent, }
            request = urllib.request.Request(self.url, None, headers)
            f = urllib.request.urlopen(request,timeout=self.timeout)
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
    """
    Re: https://www.eff.org/deeplinks/2017/03/senate-puts-isp-profits-over-your-privacy
 
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
    """

    def __init__(self,gb_per_month=gb_per_month,
                 max_links_cached=max_links_cached,
                 max_links_per_page=max_links_per_page,
                 max_links_per_domain=max_links_per_domain,
                 user_agent=user_agent,
                 search_url=search_url,
                 blacklist_url=blacklist_url,
                 wordsite_url=wordsite_url,
                 seed_bias_links=seed_bias_links,
                 timeout=timeout, diurnal_flag=True,
                 quit_driver_every_call=False,
                 blacklist=True,verbose=True):
        print('This is ISP Data Pollution 🐙💨, Version {}'.format(__version__))
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
        self.diurnal_flag = diurnal_flag
        self.quit_driver_every_call = quit_driver_every_call
        # self.gb_per_month = gb_per_month  # set in parseArgs
        # self.debug = debug  # set in parseArgs
        self.args = self.args = self.parseArgs()
        # timeout configurable decorators
        self.phantomjs_timeout = self.block_timeout(self.phantomjs_hang_handler, \
            alarm_time=self.timeout+2,errors=(self.TimeoutError,), debug=self.debug)
        self.phantomjs_short_timeout = self.block_timeout(self.phantomjs_hang_handler, \
            alarm_time=short_timeout+1,errors=(self.TimeoutError,Exception), debug=self.debug)
        self.phantomjs_quit_timeout = self.block_timeout(self.phantomjs_quit_hang_handler, \
            alarm_time=short_timeout+1,errors=(self.TimeoutError,Exception), debug=self.debug)
        self.robots_timeout = self.block_timeout(self.robots_hang_handler, \
            alarm_time=short_timeout+1,errors=(self.TimeoutError,), debug=self.debug)
        self.check_phantomjs_version()
        self.fake = Factory.create()
        self.hour_trigger = True
        self.twentyfour_hour_trigger = True
        self.domain_links = dict()
        self.start_time = time.time()
        self.data_usage = 0
        self.get_blacklist()
        self.get_random_words()
        self.pollute_forever()

    def parseArgs(self):
        parser = ap.ArgumentParser()
        parser.add_argument('-bw', '--gb_per_month', help="GB per month", type=int, default=gb_per_month)
        parser.add_argument('-mm', '--maxmemory',
            help="Maximum memory of phantomjs (MB); 0=>restart every link",
            type=int, default=1024)
        # parser.add_argument('-P', '--phantomjs-binary-path', help="Path to phantomjs binary", type=int, default=phantomjs_rss_limit_mb)
        parser.add_argument('-g', '--debug', help="Debug flag", action='store_true')
        args = parser.parse_args()
        for k in args.__dict__: setattr(self,k,getattr(args,k))
        self.sanity_check_arguments()
        return args

    def sanity_check_arguments(self):
        self.gb_per_month = min(2048,max(1,self.gb_per_month))  # min-max bandwidth limits
        if self.maxmemory == 0: self.quit_driver_every_call = True
        self.phantomjs_rss_limit_mb = min(4096,max(256,self.maxmemory))  # min-max bandwidth limits

    def check_phantomjs_version(self,recommended_version=(2,1)):
        self.open_session()
        if self.debug:
            print("{} version is {}, {} version is {}".format(self.session.capabilities["browserName"],
                                                              self.session.capabilities["version"],
                                                              self.session.capabilities["driverName"],
                                                              self.session.capabilities["driverVersion"]))
        phantomjs_version = tuple(int(i) for i in self.session.capabilities["version"].split('.'))
        if phantomjs_version < recommended_version:
            print("""{} version is {};
please upgrade to at least version {} from http://phantomjs.org.
""".format(self.session.capabilities["browserName"],self.session.capabilities["version"],
           '.'.join(str(i) for i in recommended_version)))
        self.quit_session()

    def open_session(self):
        self.quit_session()
        if not hasattr(self, 'session') or not isinstance(self.session,webdriver.phantomjs.webdriver.WebDriver):
            # phantomjs session
            # http://engineering.shapesecurity.com/2015/01/detecting-phantomjs-based-visitors.html
            # https://coderwall.com/p/9jgaeq/set-phantomjs-user-agent-string
            # http://phantomjs.org/api/webpage/property/settings.html
            # http://stackoverflow.com/questions/23390974/phantomjs-keeping-cache
            dcap = dict(DesiredCapabilities.PHANTOMJS)
            # dcap['browserName'] = 'Chrome'
            # if hasattr(self,'phantomjs_binary_path'): dcap['phantomjs.binary.path'] = ( self.phantomjs_binary_path )
            dcap['phantomjs.page.settings.userAgent'] = ( self.user_agent )
            dcap['phantomjs.page.settings.loadImages'] = ( 'false' )
            dcap['phantomjs.page.settings.clearMemoryCaches'] = ( 'true' )
            dcap['phantomjs.page.settings.resourceTimeout'] = ( max(2000,int(self.timeout * 1000)) )
            dcap['acceptSslCerts'] = ( True )
            dcap['applicationCacheEnabled'] = ( True )
            dcap['handlesAlerts'] = ( False )
            dcap['phantomjs.page.customHeaders'] = ( { 'Connection': 'keep-alive', 'Accept-Encoding': 'gzip, deflate, sdch' } )
            driver = webdriver.PhantomJS(desired_capabilities=dcap,service_args=['--disk-cache=false','--ignore-ssl-errors=false','--ssl-protocol=TLSv1.2'])
            # if hasattr(self,'phantomjs_binary_path'): driver.capabilities.setdefault("phantomjs.binary.path", self.phantomjs_binary_path)
            driver.set_window_size(1296,1018)   # Tor browser size on Linux
            driver.implicitly_wait(self.timeout+10)
            driver.set_page_load_timeout(self.timeout+10)
            self.session = driver

    def quit_session(self,hard_quit=False,pid=None,phantomjs_short_timeout_decorator=None):
        """
        close, kill -9, quit, del
        :param hard_quit: 
        :param pid: 
        :return: 
        """
        # http://stackoverflow.com/questions/25110624/how-to-properly-stop-phantomjs-execution
        if phantomjs_short_timeout_decorator is None:
            phantomjs_short_timeout_decorator = self.phantomjs_short_timeout
        if hasattr(self,'session'):
            if not hard_quit:
                @phantomjs_short_timeout_decorator
                def phantomjs_close(): self.session.close()
                phantomjs_close()
            try:
                @phantomjs_short_timeout_decorator
                def phantomjs_send_signal(): self.session.service.process.send_signal(signal.SIGTERM)
                phantomjs_send_signal()
            except Exception as e:
                if self.debug: print('.send_signal() exception:\n{}'.format(e))
                try:
                    if pid is None: pid, _ = self.phantomjs_pid_and_memory()
                except Exception as e:
                    if self.debug: print('.phantomjs_pid_and_memory() exception:\n{}'.format(e))
                try:
                    os.kill(pid, signal.SIGTERM)  # overkill (pun intended)
                except Exception as e:
                    if self.debug: print('.kill() exception:\n{}'.format(e))
            try:
                @phantomjs_short_timeout_decorator
                def phantomjs_quit(): self.session.quit()
                phantomjs_quit()
            except Exception as e:
                if self.debug: print('.quit() exception:\n{}'.format(e))
            del self.session

    def clear_session(self):
        # https://sqa.stackexchange.com/questions/10466/how-to-clear-localstorage-using-selenium-and-webdriver
        if hasattr(self, 'session'):
            try:
                @self.phantomjs_short_timeout
                def phantomjs_delete_all_cookies(): self.session.delete_all_cookies()
                phantomjs_delete_all_cookies()
            except Exception as e:
                if self.debug: print('.delete_all_cookies() exception:\n{}'.format(e))
            try:
                @self.phantomjs_short_timeout
                def phantomjs_clear():
                    self.session.execute_script('window.localStorage.clear();')
                    self.session.execute_script('window.sessionStorage.clear();')
                phantomjs_clear()
            except Exception as e:
                if self.debug: print('.execute_script() exception:\n{}'.format(e))

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
        except Exception as e:
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
        except Exception as e:
            if self.debug: print('requests exception:\n{}'.format(e))
            self.words = [ 'FUBAR' ]
        # if self.debug: print('There are {:d} words.'.format(len(self.words)))

    def pollute_forever(self):
        if self.verbose: print("""Display format:
Downloading: website.com; NNNNN links [in library], H(domain)= B bits [entropy]
Downloaded:  website.com: +LLL/NNNNN links [added], H(domain)= B bits [entropy]
""")
        self.open_session()
        self.seed_links()
        self.clear_session()
        if self.quit_driver_every_call: self.quit_session()
        while True: # pollute forever, pausing only to meet the bandwidth requirement
            try:
                if (not self.diurnal_flag) or self.diurnal_cycle_test():
                    self.pollute()
                else:
                    time.sleep(self.chi2_mean_std(3.,1.))
                if npr.uniform() < 0.005: self.set_user_agent()  # reset the user agent occasionally
                self.elapsed_time = time.time() - self.start_time
                self.exceeded_bandwidth_tasks()
                self.random_interval_tasks()
                self.every_hour_tasks()
                time.sleep(self.chi2_mean_std(0.5,0.2))
            except Exception as e:
                if self.debug: print('.pollute() exception:\n{}'.format(e))

    def pollute(self):
        if not self.quit_driver_every_call: self.check_phantomjs_process()
        if self.link_count() < 2000:
            if self.quit_driver_every_call: self.open_session()
            self.seed_links()
            self.clear_session()
            if self.quit_driver_every_call: self.quit_session()
        url = self.pop_link()
        if self.verbose: self.print_url(url)
        if self.quit_driver_every_call: self.open_session()
        self.get_url(url)
        self.clear_session()
        if self.quit_driver_every_call: self.quit_session()

    def link_count(self):
        return int(np.array([len(self.domain_links[dmn]) for dmn in self.domain_links]).sum())

    def domain_entropy(self):
        result = 0.
        domain_count = np.array([(dmn, len(self.domain_links[dmn])) for dmn in self.domain_links])
        p = np.array([np.float(c) for d, c in domain_count])
        count_total = p.sum()
        if count_total > 0:
            p = p / p.sum()
            result = self.entropy(p)
        return result

    def entropy(self,p):
        return -np.fromiter((self.xlgx(x) for x in p.flatten()),dtype=p.dtype).sum()

    def xlgx(self,x):
        x = np.abs(x)
        y = 0.
        if not (x == 0. or x == 1.):
            y = x*np.log2(x)
        return y

    def seed_links(self):
        # bias with non-random seed links
        self.bias_links()
        if self.link_count() < self.max_links_cached:
            num_words = max(1,npr.poisson(1.33)+1)  # mean of 1.33 words per search
            if num_words == 1:
                word = ' '.join(random.sample(self.words,num_words))
            else:
                if npr.uniform() < 0.5:
                    word = ' '.join(random.sample(self.words,num_words))
                else:      # quote the first two words together
                    word = ' '.join(['"{}"'.format(' '.join(random.sample(self.words, 2))),
                                     ' '.join(random.sample(self.words, num_words-2))])
            if self.debug: print('Seeding with search for \'{}\'…'.format(word))
            self.get_websearch(word)

    def bias_links(self):
        for url in self.seed_bias_links: self.add_link(url)

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
        """
        Chi-squared random variable with given mean and standard deviation.
        :param mean: 
        :param std: 
        :return: 
        """
        scale = 2.*mean/std
        nu = mean*scale
        return npr.chisquare(nu)/scale

    def exceeded_bandwidth_tasks(self):
        if self.bandwidth_test():
            self.decimate_links(total_frac=0.81,decimate_frac=0.1)
            time.sleep(120)

    def random_interval_tasks(self,random_interval=None):
        if random_interval is None: random_interval = self.chi2_mean_std(2*3600.,3600.)
        def init_random_time():
            self.random_start_time = time.time()
            self.random_interval = self.random_start_time + random_interval
        if not hasattr(self,'random_interval'): init_random_time()
        if time.time() > self.random_interval:
            init_random_time()  # reinitialize random interval
            self.current_preferred_domain = self.draw_domain()

    def every_hour_tasks(self):
        if int(self.elapsed_time/60. % 60.) == 59:
            # reset user agent, clear out cookies, seed more links
            if self.hour_trigger:
                if hasattr(self,'session'):
                    self.set_user_agent()
                    if True:
                        self.quit_session()
                        self.open_session()
                    else:
                        try:
                            @self.phantomjs_short_timeout
                            def phantomjs_delete_all_cookies(): self.session.delete_all_cookies()
                            phantomjs_delete_all_cookies()
                        except Exception as e:
                            if self.debug: print('.delete_all_cookies() exception:\n{}'.format(e))
                    self.seed_links()
                else: self.open_session()
                self.hour_trigger = False
        else:
            self.hour_trigger = True
        self.every_day_tasks()
        self.every_two_weeks_tasks()

    def every_day_tasks(self):
        if int(self.elapsed_time/3600. % 24.) == 23:
            # clear out cookies every day, decimate, and seed more links
            if self.twentyfour_hour_trigger:
                if hasattr(self,'session'):
                    self.seed_links()
                    # restart the session
                    self.quit_session()
                    self.open_session()
                else:
                    self.open_session()
                    self.decimate_links(total_frac=0.667, decimate_frac=0.1)
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
            self.decimate_links(total_frac=0.49, decimate_frac=0.333)

    def decimate_links(self, total_frac=0.81, decimate_frac=0.1, log_sampling=False):
        """ Delete `decimate_frac` of links if the total exceeds `total_frac` of the maximum allowed. """
        if self.link_count() > int(np.ceil(total_frac * self.max_links_cached)):
            for url in self.draw_links(n=int(np.ceil(self.link_count()*decimate_frac)),log_sampling=log_sampling):
                self.remove_link(url)

    def set_user_agent(self):
        global user_agent
        self.user_agent = self.fake.user_agent() if npr.random() < 0.95 else user_agent
        try:
            @self.phantomjs_short_timeout
            def phantomjs_capabilities_update():
                self.session.capabilities.update({'phantomjs.page.settings.userAgent': self.user_agent})
            phantomjs_capabilities_update()
        except Exception as e:
            if self.debug: print('.update() exception:\n{}'.format(e))

    def draw_link(self,log_sampling=True):
        """ Draw a single, random link. """
        return self.draw_links(n=1,log_sampling=log_sampling)[0]

    def draw_links(self,n=1,log_sampling=False):
        """ Draw multiple random links. """
        urls = []
        domain_array = np.array([dmn for dmn in self.domain_links])
        domain_count = np.array([len(self.domain_links[domain_array[k]]) for k in range(domain_array.shape[0])])
        p = np.array([np.float(c) for c in domain_count])
        count_total = p.sum()
        if log_sampling:  # log-sampling [log(x+1)] to bias lower count domains
            p = np.fromiter((np.log1p(x) for x in p), dtype=p.dtype)
        if count_total > 0:
            p = p/p.sum()
            cnts = npr.multinomial(n, pvals=p)
            if n > 1:
                for k in range(cnts.shape[0]):
                    domain = domain_array[k]
                    cnt = min(cnts[k],domain_count[k])
                    for url in random.sample(self.domain_links[domain],cnt):
                        urls.append(url)
            else:
                k = int(np.nonzero(cnts)[0])
                domain = domain_array[k]
                url = random.sample(self.domain_links[domain],1)[0]
                urls.append(url)
        return urls

    def draw_domain(self,log_sampling=False):
        """ Draw a single, random domain. """
        domain = None
        domain_array = np.array([dmn for dmn in self.domain_links])
        domain_count = np.array([len(self.domain_links[domain_array[k]]) for k in range(domain_array.shape[0])])
        p = np.array([np.float(c) for c in domain_count])
        count_total = p.sum()
        if log_sampling:  # log-sampling [log(x+1)] to bias lower count domains
            p = np.fromiter((np.log1p(x) for x in p), dtype=p.dtype)
        if count_total > 0:
            p = p/p.sum()
            cnts = npr.multinomial(1, pvals=p)
            k = int(np.nonzero(cnts)[0])
            domain = domain_array[k]
        return domain

    def draw_link_from_domain(self,domain):
        """ Draw a single, random link from a specific domain. """
        domain_count = len(self.domain_links.get(domain,set()))
        url = random.sample(self.domain_links[domain],1)[0] if domain_count > 0 else None
        return url

    def pop_link(self,remove_link_fraction=0.95,current_preferred_domain_fraction=0.1):
        """ Pop a link from the collected list.
If `self.current_preferred_domain` is defined, then a link from this domain is drawn
a fraction of the time. """
        url = None
        if hasattr(self,'current_preferred_domain') and npr.uniform() < current_preferred_domain_fraction:
            while url is not None:  # loop until `self.current_preferred_domain` has a url
                url = self.draw_link_from_domain(self.current_preferred_domain)
                if url is None: self.current_preferred_domain = self.draw_domain()
        if url is None: url = self.draw_link()
        if npr.uniform() < remove_link_fraction:  # 95% 1 GET, ~5% 2 GETs, .2% three GETs
            self.remove_link(url)  # pop a random item from the stack
        return url

    def add_link(self,url):
        result = False
        domain = self.domain_name(url)
        if self.link_count() < self.max_links_cached \
                and len(self.domain_links.get(domain,[])) < self.max_links_per_domain \
                and url not in self.domain_links.get(domain,set()):
            self.domain_links.setdefault(domain, set())
            self.domain_links[domain].add(url)
            result = True
            # if self.debug: print('\tAdded link \'{}\'…'.format(url))
        return result

    def remove_link(self,url):
        result = False
        domain = self.domain_name(url)
        if url in self.domain_links.get(domain,set()):
            self.domain_links[domain].remove(url)
            if len(self.domain_links[domain]) == 0:
                del self.domain_links[domain]
            result = True
        return result

    def domain_name(self,url):
        return '.'.join(uprs.urlparse(url).netloc.split('.')[-2:])

    def get_websearch(self,query):
        """
        HTTP GET of a websearch, then add any embedded links.
        :param query: 
        :return: 
        """
        url = uprs.urlunparse(uprs.urlparse(self.search_url)._replace(query='q={}&safe=active'.format(query)))
        if self.verbose: self.print_url(url)
        @self.phantomjs_timeout
        def phantomjs_get(): self.session.get(url)  # selenium driver
        phantomjs_get()
        @self.phantomjs_short_timeout
        def phantomjs_page_source(): self.data_usage += len(self.session.page_source)
        phantomjs_page_source()
        new_links = self.websearch_links()
        if self.link_count() < self.max_links_cached: self.add_url_links(new_links,url)

    def websearch_links(self):
        """
        Webpage format for a popular search engine, <div class="g">.
        :return: 
        """
        # https://github.com/detro/ghostdriver/issues/169
        @self.phantomjs_short_timeout
        def phantomjs_find_elements_by_css_selector():
            return WebDriverWait(self.session,short_timeout).until(lambda x: x.find_elements_by_css_selector('div.g'))
        elements = phantomjs_find_elements_by_css_selector()
        # get links in random order until max. per page
        k = 0
        links = []
        try:
            for div in sorted(elements,key=lambda k: random.random()):
                @self.phantomjs_short_timeout
                def phantomjs_find_element_by_tag_name(): return div.find_element_by_tag_name('a')
                a_tag = phantomjs_find_element_by_tag_name()
                @self.phantomjs_short_timeout
                def phantomjs_get_attribute(): return a_tag.get_attribute('href')
                href = phantomjs_get_attribute()
                if href is not None: links.append(href)
                k += 1
                if k > self.max_links_per_page: break
        except Exception as e:
            if self.debug: print('.find_element_by_tag_name.get_attribute() exception:\n{}'.format(e))
        return links

    def get_url(self,url):
        """
        HTTP GET of the url, and add any embedded links.
        :param url: 
        :return: 
        """
        if not self.check_robots(url): return  # bail out if robots.txt says to
        @self.phantomjs_timeout
        def phantomjs_get(): self.session.get(url)  # selenium driver
        phantomjs_get()
        @self.phantomjs_short_timeout
        def phantomjs_page_source(): self.data_usage += len(self.session.page_source)
        phantomjs_page_source()
        new_links = self.url_links()
        if self.link_count() < self.max_links_cached: self.add_url_links(new_links,url)

    def url_links(self):
        """Generic webpage link finder format."""
        # https://github.com/detro/ghostdriver/issues/169
        @self.phantomjs_short_timeout
        def phantomjs_find_elements_by_tag_name():
            return WebDriverWait(self.session,3).until(lambda x: x.find_elements_by_tag_name('a'))
        elements = phantomjs_find_elements_by_tag_name()

        # get links in random order until max. per page
        k = 0
        links = []
        try:
            for a in sorted(elements,key=lambda k: random.random()):
                @self.phantomjs_short_timeout
                def phantomjs_get_attribute(): return a.get_attribute('href')
                href = phantomjs_get_attribute()
                if href is not None: links.append(href)
                k += 1
                if k > self.max_links_per_page: break
        except Exception as e:
            if self.debug: print('.get_attribute() exception:\n{}'.format(e))
        return links

    def check_robots(self,url):
        result = True
        url_robots = uprs.urlunparse(uprs.urlparse(url)._replace(scheme='https',
            path='/robots.txt', query='', params=''))
        @self.robots_timeout
        def robots_read():
            rp = RobotFileParserUserAgent()
            rp.set_url(url_robots)
            rp.read()
            result = rp.can_fetch(self.user_agent,url)
            del rp      # ensure self.close() in urllib
            return result
        result = robots_read()
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
                @self.phantomjs_short_timeout
                def phantomjs_current_url(): return self.session.current_url
                current_url = phantomjs_current_url()
                # the current_url method breaks on a lot of sites, e.g.
                # python3 -c 'from selenium import webdriver; driver = webdriver.PhantomJS(); driver.get("https://github.com"); print(driver.title); print(driver.current_url); driver.quit()'
            except Exception as e:
                if self.debug: print('.current_url exception:\n{}'.format(e))
        if self.debug:
            print("{}: {:d} links added, {:d} total, {:.1f} bits domain entropy".format(current_url,k,self.link_count(),self.domain_entropy()))
        elif self.verbose:
            self.print_progress(current_url,num_links=k)

    def print_url(self,url):
        if self.debug: print(url + ' …')
        else: self.print_progress(url)

    def print_progress(self,url,num_links=None):
        if num_links is not None:
            text_suffix = ': +{:d}/{:d} links, H(domain)={:.1f} b'.format(num_links,self.link_count(),self.domain_entropy())
        else:
            text_suffix = '; {:d} links, H(domain)={:.1f} b …'.format(self.link_count(),self.domain_entropy())
        self.print_truncated_line(url,text_suffix)

    def print_truncated_line(self,url,text_suffix='',terminal_width=terminal_width):
        """
        Print truncated `url` + `text_suffix` to fill `terminal_width`
        :param url: 
        :param text_suffix: 
        :param terminal_width: 
        :return: 
        """
        chars_used = len(text_suffix)
        if text_suffix == '…':
            if len(url) >= terminal_width:
                url = url[:terminal_width-1]  # add '…' below
            elif len(url) < terminal_width-1:
                url += ' '  # add an extra space before the ellipsis
        else:
            if len(url) + chars_used > terminal_width:
                url = url[:terminal_width-chars_used-1] + '…'
        text = "{}{}".format(url,text_suffix)  # added white space necessary
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
    # configurable decorator to timeout phantomjs and robotparser calls
    # http://stackoverflow.com/questions/15572288/general-decorator-to-wrap-try-except-in-python
    # Syntax:
    # phantomjs_timeout = block_timeout(phantomjs_hang_handler)
    # @phantomjs_timeout
    # def phantomjs_block():
    #     # phantomjs stuff
    #     pass
    # phantomjs_block()

    def block_timeout(self,hang_handler, alarm_time=timeout, errors=(Exception,), debug=False):
        def decorator(func):
            def call_func(*args, **kwargs):
                signal.signal(signal.SIGALRM, hang_handler)  # register hang handler
                signal.alarm(alarm_time)  # set an alarm
                result = None
                try:
                    result = func(*args, **kwargs)
                except errors as e:
                    if debug: print('{} exception:\n{}'.format(func.__name__, e))
                finally:
                    signal.alarm(0)  # cancel the alarm
                return result
            return call_func
        return decorator

    class TimeoutError(Exception):
        pass

    def phantomjs_hang_handler(self, signum, frame):
        # https://github.com/detro/ghostdriver/issues/334
        # http://stackoverflow.com/questions/492519/timeout-on-a-function-call
        if self.debug: print('Looks like phantomjs has hung.')
        try:
            self.quit_session(phantomjs_short_timeout_decorator=self.phantomjs_quit_timeout)
        except Exception as e:
            if self.debug: print(e)
        self.open_session()

    def phantomjs_quit_hang_handler(self, signum, frame):
        raise self.TimeoutError('phantomjs .quit method is taking too long')

    def robots_hang_handler(self, signum, frame):
        if self.debug: print('Looks like robotparser has hung.')
        raise self.TimeoutError('robotparser is taking too long')

    def check_phantomjs_process(self):
        """
        Check if phantomjs is running.
        :return: 
        """
        # Check rss and restart if too large, then check existence
        # http://stackoverflow.com/questions/568271/how-to-check-if-there-exists-a-process-with-a-given-pid-in-python
        try:
            if not hasattr(self,'session'): self.open_session()
            pid, rss_mb = self.phantomjs_pid_and_memory()
            if rss_mb > self.phantomjs_rss_limit_mb:  # memory limit
                self.quit_session(pid=pid)
                self.open_session()
                pid, _ = self.phantomjs_pid_and_memory()
            # check existence
            os.kill(pid, 0)
        except (OSError,psutil.NoSuchProcess,Exception) as e:
            if self.debug: print('.phantomjs_pid_and_memory() exception:\n{}'.format(e))
            if issubclass(type(e),psutil.NoSuchProcess):
                raise Exception("There's a phantomjs zombie, and the thread shouldn't have reached this statement.")
            return False
        else:
            return True

    def phantomjs_pid_and_memory(self):
        """ Return the pid and memory (MB) of the phantomjs process,
        restart if it's a zombie, and exit if a restart isn't working
        after three attempts. """
        for k in range(3):    # three strikes
            try:
                @self.phantomjs_short_timeout
                def phantomjs_process_pid(): return self.session.service.process.pid
                pid = phantomjs_process_pid()
                rss_mb = psutil.Process(pid).memory_info().rss / float(2 ** 20)
                break
            except (psutil.NoSuchProcess,Exception) as e:
                if self.debug: print('.service.process.pid exception:\n{}'.format(e))
                self.quit_session(pid=pid)
                self.open_session()
        else:  # throw in the towel and exit if no viable phantomjs process after multiple attempts
            sys.exit()
        return (pid, rss_mb)

if __name__ == "__main__":
    ISPDataPollution()
