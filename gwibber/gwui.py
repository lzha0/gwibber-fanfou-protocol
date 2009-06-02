"""

Gwibber Client Interface Library
SegPhault (Ryan Paul) - 05/26/2007

"""

from . import gintegration, resources, config
import webkit, gtk, copy
import urllib2, hashlib, os, simplejson
from mako.template import Template
from mako.lookup import TemplateLookup
import Image

# i18n magic
import gettext

_ = gettext.lgettext

DEFAULT_UPDATE_INTERVAL = 1000 * 60 * 5
IMG_CACHE_DIR = os.path.join(resources.CACHE_BASE_DIR, "gwibber", "images")
DEFAULT_AVATAR = 'http://digg.com/img/udl.png'

class Color:
  def __init__(self, hex):
    self.hex = hex
    self.dec = int(hex.replace("#", ""), 16)
    self.r = (self.dec >> 16) & 0xff
    self.g = (self.dec >> 8) & 0xff
    self.b = self.dec & 0xff
    self.rgb = "%s, %s, %s" % (self.r, self.g, self.b)

  @classmethod
  def from_gtk_color(self, c):
    if isinstance(c, gtk.gdk.Color): c = str(c)
    return self("#" + "".join([c[1:3], c[5:7], c[9:11]]))

def get_theme_colors(w):
  d = {}
  
  for i in ["base", "text", "fg", "bg"]:
    d[i] = Color.from_gtk_color(
      getattr(w.get_style(), i)[gtk.STATE_NORMAL].to_string())

    d["%s_selected" % i] = Color.from_gtk_color(
      getattr(w.get_style(), i)[gtk.STATE_SELECTED].to_string())

  return d

class MessageView(webkit.WebView):
  def __init__(self, theme, client):
    webkit.WebView.__init__(self)
    self.client = client
    self.load_externally = True
    self.connect("navigation-requested", self.on_click_link)
    self.message_store = []
    self.data_retrieval_handler = None
    self.settings = webkit.WebSettings()
    self.set_settings(self.settings)
    self.load_theme(theme)

  def load_theme(self, theme):
    if not resources.get_theme_path(theme): theme = 'default'
    self.theme = theme

    if self.client.preferences["override_font_options"]:
      fstring = self.client.preferences["default_font"]
    else:
      fstring = config.GCONF.get_string("/desktop/gnome/interface/font_name")

    if fstring:
      fname, fsize = fstring.rsplit(None, 1)
      self.settings.set_property("default-font-family", fname)
      self.settings.set_property("sans-serif-font-family", fname)
      self.settings.set_property("serif-font-family", fname)
      self.settings.set_property("default-font-size", (int(fsize) + 2))

  def load_messages(self, message_store = None):
    for n, m in enumerate(self.message_store):
      m.message_index = n

      if m.account[m.bgcolor]:
        m.color = Color.from_gtk_color(m.account[m.bgcolor])

    theme_path = resources.get_theme_path(self.theme)
    template_path = os.path.join(theme_path, "template.mako")
    template_lookup_paths = list(resources.get_template_dirs()) + [theme_path]

    template = Template(
      open(template_path).read(),
      lookup=TemplateLookup(directories=template_lookup_paths))
    
    content = template.render(
        message_store=self.message_store,
        theme=get_theme_colors(self),
        resources=resources,
        preferences=self.client.preferences,
        _=_)
    
    def on_finish_load(v, f, vscroll_pos):
      self.scroll.get_vadjustment().set_value(vscroll_pos)

    self.connect("load-finished", on_finish_load, self.scroll.get_vadjustment().get_value())
    self.load_html_string(content, "file://%s/" % resources.get_theme_path(self.theme))

  def on_click_link(self, view, frame, req):
    uri = req.get_uri()
    if uri.startswith("file:///"): return False
    
    if not self.link_handler(uri, self) and self.load_externally:
      gintegration.load_url(uri)
    return self.load_externally

  def link_handler(self, uri):
    pass

class UserView(MessageView):
  def load_messages(self, message_store = None): # override
    if (self.message_store and len(self.message_store) > 0):
      # use info from first message to create user header
      #msg = simplejson.dumps(dict(self.message_store[0].__dict__, message_index=0), sort_keys=True, indent=4, default=str)
      #self.execute_script("addUserHeader(%s)" % msg)
      # display other messages as normal
      
      header = copy.copy(self.message_store[0])
      header.is_user_header = True
      self.message_store.insert(0, header)
      MessageView.load_messages(self, message_store)

def image_cache(url, cache_dir = IMG_CACHE_DIR):
  if not os.path.exists(cache_dir): os.makedirs(cache_dir)
  encoded_url = hashlib.sha1(url).hexdigest()
  if len(encoded_url) > 200: encoded_url = encoded_url[::-1][:200]
  fmt = url.split('.')[-1] # jpg/png etc.
  if "friendfeed" in url: fmt = "jpg" # HATE
  img_path = os.path.join(cache_dir, encoded_url + '.' + fmt).replace("\n", "")

  if not os.path.exists(img_path):
    output = open(img_path, "w+")
    try:
      image_data = urllib2.urlopen(url).read()
      if image_data.startswith("<?xml"):
        raise IOError()

      output.write(urllib2.urlopen(url).read())
      output.close()
      try:
        image = Image.open(img_path)
        (x, y) = image.size
        if x != 48 or y != 48:
          if image.mode == 'P': # need to upsample limited palette images before resizing
            image = image.convert('RGBA') 
          image = image.resize((48, 48), Image.ANTIALIAS)
          image.save(img_path)
      except Exception, e:
        from traceback import format_exc
        print(format_exc())
    except IOError, e:
      if hasattr(e, 'reason'): # URLError
        print('image_cache URL Error: %s whilst fetching %s' % (e.reason, url))
      elif hasattr(e, 'code') and hasattr(e, 'msg') and hasattr(e, 'url'): # HTTPError
        print('image_cache HTTP Error %s: %s whilst fetching %s' % (e.code, e.msg, e.url))
      else:
        print(e)
      # if there were any problems getting the avatar img replace it with default
      output.write(urllib2.urlopen(DEFAULT_AVATAR).read())
    finally:
      output.close()

  return img_path
