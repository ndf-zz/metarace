
from xml.sax.saxutils import escape, quoteattr
import sys

"""HTML output lib.

Cheap and nasty functional primitives for HTML output. Each primitive
outputs a single string. No checking is performed on the structure of
the document produced. All elements take a named parameter 'attrs'
which is a dict of key/value attributes. Non-empty elements take a
parameter 'clist' which is a list of other constructed elements.

Example for an empty element:

    hr(attrs={'id':'thehr'})

Example for an element with content:

    a(['link text'], attrs={'href':'#target'})

Example paragraph:

    p(['Check the',
       a(['website'], attrs={'href':'#website'}),
       'for more.'])

"""

def html(headlist=[], bodylist=[]):
    """Emit HTML document."""
    return '\n'.join([
      preamble(),
      '<html lang="en">',
      head(headlist),
      body(bodylist),
      '</html>'])

def preamble():
    """Emit HTML preamble."""
    return '<!DOCTYPE html>'

def attrlist(attrs):
    """Convert attr dict into properly escaped attrlist."""
    alist = []
    for a in attrs:
        alist.append(a.lower() + '=' + quoteattr(attrs[a]))
    if len(alist) > 0:
        return ' ' + ' '.join(alist) 
    else:
        return ''

def escapetext(text=''):
    """Return escaped copy of text."""
    return escape(text, {'"':'&quot;'})

def tablestyles():
    """Emit the fixed table styles."""
    return '\ntable.middle td { vertical-align: middle; }\n th.center { text-align: center; }\n th.right { text-align: right; }\n td.right { text-align: right; }\n'

def shim(shivlink, respondlink):
    """Emit the HTML5 shim for IE8."""
    return '\n<!--[if le IE 9]>\n<script src=' + quoteattr(shivlink) + '>\n</script>\n<script src=' + quoteattr(respondlink) + '>\n</script>\n<![endif]-->\n'

def comment(commentstr=''):
    """Insert comment."""
    return '<!-- ' + commentstr.replace('--','') + ' -->'

# Declare all the empty types
for empty in ['meta', 'link', 'base', 'param',
              'hr', 'br', 'img', 'col']:
    def emptyfunc(attrs={}, elem=empty):
        return '<' + elem + attrlist(attrs) + '>'
    setattr(sys.modules[__name__], empty, emptyfunc) 

# Declare all the non-empties
for nonempty in ['head', 'body', 'title', 'div', 'style', 'script',
                 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                 'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'address',
                 'pre', 'blockquote', 'a', 'span', 'em', 'strong',
                 'dfn', 'code', 'samp', 'kbd', 'var', 'cite',
                 'abbr', 'acronym', 'q', 'sub', 'sup', 'tt',
                 'i', 'big', 'small', 'label', 'form', 'select',
                 'optgroup', 'option', 'textarea', 'fieldset',
                 'legend', 'button', 'table', 'caption',
                 'thead', 'tfoot', 'tbody', 'colgroup',
                 'tr', 'th', 'td', ]:
    def nonemptyfunc(clist=[], attrs={}, elem=nonempty):
        if isinstance(clist, str):
            clist = [clist]
        return('<' + elem + attrlist(attrs) + '>'
                + '\n'.join(clist) + '</' + elem + '>')
    setattr(sys.modules[__name__], nonempty, nonemptyfunc) 

# output a valid but empty html templatye
def emptypage():
    return html([
                           meta(attrs={'charset':'utf-8'}),
           meta(attrs={'http-equiv':'X-UA-Compatible',
                       'content':'IE=edge'}),
           meta(attrs={'name':'viewport',
                       'content':'width=device-width, initial-scale=1'}),
           title('__REPORT_TITLE__'),
           link(attrs={'href':'bootstrap.min.css',
                       'rel':'stylesheet'}),
           style(tablestyles(), {'type':'text/css'}),
           shim('html5shiv.min.js',
                'respond.min.js'),
                ],
                div([h1('__REPORT_TITLE__'),
                     '\n', comment('Begin report content'),
                     '__REPORT_CONTENT__',
                     comment('End report content'),'\n',
                     script('\n', attrs={'src':'jquery.min.js'}),
                     script('\n', attrs={'src':'bootstrap.min.js'}),
                 ],
                    attrs={'class':'container'}))

