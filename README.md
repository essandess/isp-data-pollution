# ISP Data Pollution

Congress's party-line vote will allow ISP's to exploit your family's private data without your consent. See "**[Senate Puts ISP Profits Over Your Privacy](https://www.eff.org/deeplinks/2017/03/senate-puts-isp-profits-over-your-privacy)**".

This script is designed to defeat this violation by generating large amounts of realistic, random web browsing to pollute ISP data and render it effectively useless by obfuscating actual browsing data.

I pay my ISP a lot for data usage every month. I typically don't use all the bandwidth that I pay for. If my ISP is going to sell private browsing habits, then I'm going to pollute browsing with noise and use all the bandwidth that I pay for. This method accomplishes this.

If everyone uses all the data they've paid for to pollute their browsing history, then perhaps ISPs will reconsider the business model of selling customer's private browsing history.

The [alternative](https://arstechnica.com/information-technology/2017/03/how-isps-can-sell-your-web-history-and-how-to-stop-them/) of using a VPN or Tor merely pushes the issue onto to the choice of VPN provider, complicates networking, and adds the real issue of navigating captchas when appearing as a Tor exit node. Also, merely encrypted traffic has too much [exploitable side-channel information](https://www.theatlantic.com/technology/archive/2017/03/encryption-wont-stop-your-internet-provider-from-spying-on-you/521208/), and could still be used to determine when specific family members are at home, and the activities in which they're engaged.

This crawler uses the Python selenium, phantomjs, and lxml.html libraries, uses blacklists for undesirable websites (see the code for details), does not download images, and respects robots.txt, which all provide good security.

# Privatizing Proxy Filter with VPN Access

Data pollution is one component of privatizing your personal data. Install the [EFF](../../../../EFForg)'s [HTTPS Everywhere](https://www.eff.org/https-everywhere) on **all** browsers. Also see the repos [osxfortress](../../../osxfortress) and [osx-openvpn-server](../../../osx-openvpn-server) to block advertising, trackers, and malware across devices.

# Example crawl

A fews seconds of random crawling looks like this:

```
Added 1 links, 29045 total at url 'https://www.diapers.com/l/best-gifts-for-mom?ref=b_scf_leg_best_gifts_for_mom&icn=b_scf_leg&ici=best_gifts_for_mom'.
Added 1 links, 29045 total at url 'http://bananarepublic.gap.eu/browse/category.do?cid=1025790'.
Added 200 links, 29244 total at url 'http://www.bananarepublic.ca/products/mens-suits.jsp'.
Added 1 links, 29244 total at url 'http://cyworld.com.cy/en/jurisdictions/estonia7'.
Added 1 links, 29244 total at url 'http://bananarepublic.gap.eu/browse/category.do?cid=1025788'.
Added 2 links, 29245 total at url 'https://www.osti.gov/scitech/biblio/1337873-cyber-threat-vulnerability-analysis-electric-sector'.
Added 1 links, 29245 total at url 'https://www.amazon.com/30th-Anniversary-Collection-Time-Greatest/dp/B00000334E/ref=sr_1_9/153-5801643-0200824?ie=UTF8&qid=1491060352&sr=8-9&keywords=Paul+Anka'.
Added 40 links, 29284 total at url 'http://www.bendixking.com/Products/Displays'.
Added 1 links, 29284 total at url 'http://www.thefreedictionary.com/arid'.
Added 47 links, 29330 total at url 'http://www2.beltrailway.com/unemployment-sickness-benefits-for-railroad-employees/'.
```

The screenshot of a randomly crawled web page looks like this. Note that there are no downloaded images.

`driver.get_screenshot_as_file('his_all_time_greatest_hits.png')`:

![His All Time Greatest Hits](his_all_time_greatest_hits.png)

# Running

`python3 isp_data_pollution.py`

# Installation

This is what was necessary on macOS:

```
sudo port install selenenium phantomjs
sudo -H pip-3.4 install selenium

# if phantonjs fails to build because of an Xode configuration error: test with
/usr/bin/xcrun -find xcrun
# then do this:
cd /Applications/Xcode.app/Contents/Developer/usr/bin/
sudo ln -s xcodebuild xcrun
```
