#!/usr/bin/python2.5

import os
import sys

APP_DIR = os.path.abspath(os.path.dirname(__file__))
THIRD_PARTY = os.path.join(APP_DIR, 'third_party')
sys.path.insert(0, THIRD_PARTY)

import html5lib
import html5lib.treebuilders
import logging
import re
import simplejson

from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app


TEMPLATE_DIR = 'templates'

EXAMPLE_SHORT_URL = 'http://goo.gl/ItuoN'

UNSAFE_JSON_CHARS = re.compile(r'[^\w\d\-\_]')

class ReportableError(Exception):
  """A class of exceptions that should be shown to the user."""
  message = None

  def __init__(self, message):
    """Constructs a new ReportableError.

    Args:
      message: The message to be logged and displayed to the user.
    """
    self.message = message


class UserError(ReportableError):
  """An 400 error caused by user behavior."""


class ServerError(ReportableError):
  """An 500 error caused by the server."""


class Usage(webapp.RequestHandler):
  """Prints usage information in response to requests to '/'."""
  def get(self):
    self.response.headers['Content-Type'] = 'text/html'
    path = os.path.join(os.path.dirname(__file__), TEMPLATE_DIR, 'usage.tmpl')
    template_vars = {'example_short_url': EXAMPLE_SHORT_URL}
    self.response.out.write(template.render(path, template_vars))


class Unshorten(webapp.RequestHandler):
  """A request handler that unshortens URLs."""

  def get(self):
    """Unshortens the URL specified by the 'url' param."""
    
    url = self.request.get('url', default_value=None)
    if not url:
      raise UserError("The 'url' parameter is required.")
    data = memcache.get(url)
    if not data:
      data = self._unshorten_url(url)
      if data:
        memcache.set(url, data)
    callback = self._sanitize_callback(self.request.get('callback'))
    if callback:
      self._print('%s(%s)' % (callback, simplejson.dumps(data)))
    else:
      self._print(simplejson.dumps(data, sort_keys=True, indent=4))

  def handle_exception(self, exception, debug_mode):
    if isinstance(exception, UserError):
      logging.error('ServerError: %s' % exception.message)
      self.error(400)
      self._print_error(exception.message)
    elif isinstance(exception, ServerError):
      logging.error('SeverError: %s' % exception.message)
      self.error(500)
      self._print_error(exception.message)
    else:
      super(Unshorten, self).handle_exception(exception, debug_mode)

  def _print(self, content):
    self.response.headers['Content-Type'] = 'application/json'
    self.response.out.write(content)
    self.response.out.write("\n")

  def _print_error(self, message):
    """Prints an error message as type text/plain.

    Args:
      error: The plain text error message.
    """
    self.response.headers['Content-Type'] = 'text/plain'
    self.response.out.write(message)
    self.response.out.write("\n")

  def _unshorten_url(self, url):
    """Fetches a URL and returns a dict containing the target of the redirects (if any)

    Args:
      url: The URL to be unshortened
    """
    response = self._get_url(url)
    title = self._extract_title(response.content)
    return {'url': url,
            'content-location': response.final_url,
            'content-type': response.headers['Content-Type'],
            'title': title}

  def _extract_title(self, content):
    parser = html5lib.HTMLParser(tree=html5lib.treebuilders.getTreeBuilder("dom"))
    doc = parser.parse(content)
    if doc == None:
      return None
    title_node = doc.getElementsByTagName("title")[0]
    if title_node == None:
      return None
    return self._get_text(title_node.childNodes).strip()

  def _get_text(self, nodelist):
    rc = []
    for node in nodelist:
      if node.nodeType == node.TEXT_NODE:
        rc.append(node.data)
    return ''.join(rc)

  def _get_url(self, original_url):
    """Retrieves a URL and caches the results.

    Args:
      url: A url to be fetched
    """
    url = original_url
    if not url.startswith('http') and not url.startswith('https'):
      url = 'http://%s' % original_url
    try:
      response = urlfetch.fetch(url, deadline=10, follow_redirects=True, allow_truncated=True)
    except Exception, e:  # This is hackish
      raise ServerError('Could not fetch %s. Host down?' % url)
    if response.status_code != 200:
      raise ServerError(
        "Could not fetch url '%s': %s." % (url, response.status_code))
    if not response.content:
      raise ServerError(
        "Could not fetch url '%s': %s." % (url, response.status_code))
    if not response.final_url:
      response.final_url = url
    return response

  def _sanitize_callback(self, string):
    """Only allow valid json function identifiers through"""
    if UNSAFE_JSON_CHARS.search(string):
      return None
    else:
      return string


application = webapp.WSGIApplication([('/unshorten/?', Unshorten),
                                      ('/', Usage)],
                                     debug=True)


def main():
  run_wsgi_app(application)


if __name__ == "__main__":
  main()
