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

''' Tweedhat - A personal non-feature-complete twitter client 
        *** Very hacked together bad code! ***
        Depends on QT for gui _AND_ gtk for libnotify
        Also depends on tweepy and pynotify for libnotify
        Due to tweepy, written for python2
        Some threading has to be done for updates
        Handle connection failures and rate limiting
'''
import pickle
from pickle import UnpicklingError
import signal
import sys
import gtk
import re
import webbrowser
import hashlib
import os

import pynotify

from collections import OrderedDict

import tweepy

import sip
import urllib
sip.setapi('QString', 2)

from PyQt4.QtGui import QMainWindow, QApplication, QLineEdit, QInputDialog, QDesktopServices, QClipboard, QMessageBox, QListWidget, QListView, QListWidgetItem, QAbstractItemView, QLabel, QFrame, QStyleOptionViewItem
from PyQt4.Qt import QTimer
from PyQt4.QtCore import QUrl, QSize, Qt

CONSUMER_KEY = '6IHt18mkSmjT97cSAYHPuQ'
CONSUMER_SECRET = 'hDsZuhnLmgz5G2nxK9TNpfgXQL0wx9MrMcssPFPXM'
APP_NAME = 'TweedHat'

pynotify.init(APP_NAME)

def handle_quit(*k):
    QApplication.quit()

icon_cache = {}

def iconify(url):
    urlhash = hashlib.sha256(url).hexdigest()[:16]
    imgdir = QApplication.instance().imagescachedir
    imgpath = os.path.join(imgdir, urlhash)
    if os.path.exists(imgpath):
        f = open(imgpath)
    else:
        webf = urllib.urlopen(url)
        f = open(imgpath, 'w')
        f.write(webf.read())
        f = open(imgpath)
    data = f.read()
    
    pbl = gtk.gdk.PixbufLoader()
    pbl.write(data)
    pbuf = pbl.get_pixbuf()
    pbl.close()
    
    
    item = (pbuf, imgpath)
    icon_cache[url] = item
    return item

def icon_cached(url, w):
    try:
        item = icon_cache[url] if url in icon_cache else iconify(url)
        return item[w]
    except IOError:
        print "%s failed" % url
        return None

def gtkonify(url):
    return icon_cached(url, 0)
    
def iqonify(url):
    return icon_cached(url, 1)

class TweetListWidget(QListWidget):
    def __init__(self):
        QListWidget.__init__(self)
        self.setSelectionMode(QAbstractItemView.NoSelection)

urlify_regex = re.compile(r"((http|https)://[^ ]+)")
def urlify(text):
    return urlify_regex.sub(r'<a href="\1">\1</a>', text)

class TweetWidget(QLabel):
    def __init__(self, tweet):
        text = ''
        rt = getattr(tweet, 'retweeted_status', None)
        if rt:
            text = '<br/><i>Retweeted by @%s</i>' % (tweet.user.screen_name)
            tweet = rt
        text = '<img src="%s" width="48px" ><div style="margin-left: 50px;">%s</b>  <i>@%s</i><br/><br/>%s%s</div>' % (iqonify(tweet.user.profile_image_url), tweet.user.name, tweet.user.screen_name, urlify(tweet.text.strip()), text)
        QLabel.__init__(self)
        self.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.setOpenExternalLinks(True)
        self.setWordWrap(True)
        self.setText(text)
        self.tweet = tweet

class MainWindow(QMainWindow):
    def current(self):
        return self.tweets.itemAt(0, 0)
    
    def scroll_changed(self):
        current = self.current()
        if not current:
            return
        id = current.tweet_id
        if self.latest is None or id > self.latest:
            self.app.set_latest_seen_tweet(id)
            self.latest = id
    
    def add_tweets(self, tweets):
        old_item = self.current()
        latest_first = None
        for t in tweets:
            widget = TweetWidget(t)
            
            widget.adjustSize()
            tw = QListWidgetItem(None)
            tw.tweet_id = t.id
            height = widget.height()
            tw.setSizeHint(QSize(0, height))
            self.tweets.insertItem(0, tw)
            self.tweets.setItemWidget(tw, widget)
            if self.latest and t.id == self.latest:
                latest_first = tw
        old_item = old_item if old_item else latest_first
        if old_item:
            self.tweets.scrollToItem(old_item, QAbstractItemView.PositionAtTop)
    
    def initial(self, tweets):
        self.add_tweets(tweets)
    
    def notify(self, title, text, icon_url=None):
        icon_url = self.app.user.profile_image_url if not icon_url else icon_url
        n = pynotify.Notification(title, text)
        icon = gtkonify(icon_url)
        if icon:
            n.set_icon_from_pixbuf(icon)
        n.show()
    
    def update(self, tweets):
        self.add_tweets(tweets)
        
        if len(tweets) == 1:
            tweet = tweets[0]
            icon = tweet.user.profile_image_url
            self.notify('New tweet by %s' % tweet.user.name, tweet.text, icon)
        else:
            self.notify('New tweets', '%d new tweets available' % len(tweets))
    
    def __init__(self):
        QMainWindow.__init__(self)
        self.app = QApplication.instance()
        self.tweets = TweetListWidget()
        self.latest = self.app.get_latest_seen_tweet()
        self.setCentralWidget(self.tweets)
        self.setWindowTitle(self.app.name)
        self.tweets.verticalScrollBar().valueChanged.connect(self.scroll_changed)
    
class TweedHat(QApplication):
    def set_latest_seen_tweet(self, tweet):
        pickle.dump(tweet, open(self.latestseenfilename, 'w'))
    
    def get_latest_seen_tweet(self):
        try:
            return pickle.load(open(self.latestseenfilename))
        except (IOError, UnpicklingError):
            pass
    
    def quiting(self):
        self.save()
    
    def save(self):
        try:
            pickle.dump(self.tweets, open(self.tweetsfilename, 'w'))
        except (NameError, IOError, UnpicklingError):
            pass
    
    def load(self):
        try:
            self.tweets = pickle.load(open(self.tweetsfilename))
        except IOError, pickle.UnpicklingError:
            self.tweets = OrderedDict()
    
    def update(self, update=True):
        try:
            self._update(update)
        except tweepy.TweepError as e:
            print "Got error %s, reconnecting" %  e
            if self.timer:
                self.timer.stop()
            self.ready()
    
    def _update(self, update):
        initial = not self.tweets and not update
        sys.stdout.write('checking for new tweets...')
        endpoint = self.api.home_timeline
        kw = {}
        count = 50
        tweets = [t for t in endpoint(count=count, **kw)]
        min_new_tweet = tweets[-1].id
        max_new_tweet = tweets[0].id
        max_tweet = max(self.tweets) if self.tweets else None
        current = min_new_tweet
        if initial:
            sys.stdout.write('\ndownloading entire twitter history available on your home timeline...please wait...this will take some time')
            try:
                os.unlink(self.latestseenfilename)
            except OSError:
                pass
            try:
                os.unlink(self.tweetsfilename)
            except OSError:
                pass

        while max_tweet is None or min_new_tweet > max_tweet:
            sys.stdout.write('...')
            sys.stdout.flush()
            t = [t for t in endpoint(count=count, max_id=current, **kw)]
            if not t:
                break
            min_t = t[-1].id
            max_t = t[0].id
            if max_tweet is not None and max_t >= max_tweet:
                break
            if min_t >= current:
                break
            current = min_t
            tweets += t
        print 'done'
        added_new = []
        tweets.reverse() # We want oldest to newest
        for t in tweets:
            if max_tweet is not None and t.id <= max_tweet:
                continue
            if t.id not in self.tweets:
                added_new.append(t)
                self.tweets[t.id] = t
        if added_new and update:
            self.window.update(added_new)
        elif not update:
            self.window.initial(added_new)
            if initial:
                self.window.scroll_changed()
        if added_new:
            print '%d new tweet(s)' % len(added_new)
        elif initial:
            print 'got %d tweets' % len(self.tweets)
        else:
            print 'no new tweets'
        self.save()
        
    
    def init(self):
        '''
            TODO: MAKE LESS CONFUSING NESTED LOOPS!
            Inits oauth and asks for the PIN and all that
            Returns false if the application if the application should not continue
        '''
        ready = False
        auth = tweepy.OAuthHandler(self.key, self.secret)
        oauthfilename = os.path.join(self.dir, 'oauth')
        
        while True:
            try:
                existing = pickle.load(open(oauthfilename))
                auth.set_access_token(existing.key, existing.secret)
            except IOError, pickle.UnpicklingError:
                while True:
                    url = auth.get_authorization_url()
                    self.clipboard().setText(url)
                    QDesktopServices.openUrl(QUrl(url))
                    pin, ok = QInputDialog.getText(self.window, 'Enter PIN', 'Enter PIN')
                    pin = pin.strip()
                    if not ok:
                        return False
                    if pin:
                        try:
                            auth.get_access_token(pin)
                        except tweepy.TweepError as e:
                            continue
                        pickle.dump(auth.access_token, open(oauthfilename, 'w'))
                        break
            self.api = tweepy.API(auth)
            if not self.api.verify_credentials():
                try:
                    os.unlink(oauthfilename)
                except OSError:
                    pass
            else:
                break
        self.backoff = 1
        self.user = self.api.me()
        self.update(bool(self.tweets))
        return True
    
    def ready(self):
        try:
            if not self.init():
                self.quit()
        except tweepy.TweepError as e:
            try:
                status = self.api.rate_limit_status()
                timeleft = status.reset_time_in_seconds
                print "Rate limited for another %d seconds" % timeleft
                QTimer.singleShot((timeleft+1)*1000, self.ready)
                return
            except tweepy.TweepError:
                print "Twitter init error: %s, trying again in %d seconds" % (e, self.backoff)
                QTimer.singleShot((self.backoff*1000), self.ready)
                self.backoff *= 2
                self.backoff = min(self.backoff, 60)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(self.rate)
    
    def exec_(self):
        if self.tweets:
            self.window.initial([t for t in self.tweets.values()])
            QTimer.singleShot(100, self.ready)
        else:
            self.ready()
        self.window.show()
        return QApplication.exec_()
    
    def __init__(self, name=APP_NAME, key=CONSUMER_KEY, secret=CONSUMER_SECRET, rate_seconds=180):
        self.name = name
        self.backoff = 1
        self.rate = rate_seconds * 1000
        self.dir = os.path.expanduser('~/.%s/' % self.name.lower())
        if not os.path.exists(self.dir):
            os.makedirs(self.dir)
        self.key = key
        self.timer = None
        self.tweetsfilename = os.path.join(self.dir, 'tweets')
        self.latestseenfilename = os.path.join(self.dir, 'latestseen')
        self.imagescachedir = os.path.join(self.dir, 'cached_images/')
        if not os.path.exists(self.imagescachedir):
            os.makedirs(self.imagescachedir)
        self.load()
        self.api = None
        self.secret = secret
        QApplication.__init__(self, sys.argv)
        self.aboutToQuit.connect(self.quiting)
        self.window = MainWindow()
    
def main():
    app = TweedHat()
    signal.signal(signal.SIGINT, handle_quit)
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(100) # Give python some time away from QT every 100ms
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
