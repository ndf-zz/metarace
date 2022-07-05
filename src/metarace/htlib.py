"""HTML output library.

Cheap and nasty functional primitives for HTML output. Each primitive
returns a single string. No checking is performed on the structure of
the document produced. All elements take a named parameter 'attrs'
which is a dict of key/value attributes. Non-empty elements take a
parameter 'clist' which is a list of other constructed elements.

Note: <input> is provided by forminput()

Example for an empty element:

    hr(attrs={'id':'thehr'}) => <hr id="thehr">

Example for an element with content:

    a(['link text'], attrs={'href':'#target'}) => 

	<a href="#target">link text</a>

Example paragraph:

    p(('Check the',
       a(('website'), attrs={'href':'#website'}),
       'for more.')) => 

	<p>Check the\n<a href="#website">website</a>\nfor more.</p>

"""

from xml.sax.saxutils import escape, quoteattr
import sys


def html(headlist=(), bodylist=(), attrs=None):
    """Emit HTML document."""
    bodyattrs = {'onload': 'ud();'}
    if attrs is not None:
        bodyattrs = attrs
    return '\n'.join((preamble(), '<html lang="en">', head(headlist),
                      body(bodylist, bodyattrs), '</html>'))


def preamble():
    """Emit HTML preamble."""
    return '<!doctype html>'


def attrlist(attrs):
    """Convert attr dict into escaped attrlist."""
    alist = []
    for a in attrs:
        alist.append(a.lower() + '=' + quoteattr(attrs[a]))
    if len(alist) > 0:
        alist.insert(0, '')
        return ' '.join(alist)
    else:
        return ''


def escapetext(text=''):
    """Return escaped copy of text."""
    return escape(text, {'"': '&quot;'})


def comment(commentstr=''):
    """Insert comment."""
    return '<!-- ' + commentstr.replace('--', '') + ' -->'


# output a valid but empty html templatye
def emptypage():
    return html((
        meta(attrs={'charset': 'utf-8'}),
        meta(attrs={
            'name': 'viewport',
            'content': 'width=device-width, initial-scale=1'
        }),
        title('__REPORT_TITLE__'),
        link(
            attrs={
                'href':
                'https://cdn.jsdelivr.net/npm/bootstrap@5.0.2/dist/css/bootstrap.min.css',
                'integrity':
                'sha384-EVSTQN3/azprG1Anm3QDgpJLIm9Nao0Yz1ztcQTwFspd3yD65VohhpuuCOmLASjC',
                'crossorigin': 'anonymous',
                'rel': 'stylesheet'
            }),
        link(
            attrs={
                'href':
                'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.3/font/bootstrap-icons.css',
                'rel': 'stylesheet'
            }),
        script((
            'function ud(){null!==document.querySelector("#pgre")&&setTimeout("history.go(0);",55329)}function rl(){return setTimeout("history.go(0);",10),!1}',
        )),
    ), ('__REPORT_NAV__',
        div((
            h1('__REPORT_TITLE__'),
            '__REPORT_CONTENT__',
        ),
            attrs={'class': 'container'})))


# Declare all the empty types
for empty in ('meta', 'link', 'base', 'param', 'hr', 'br', 'img', 'col'):

    def emptyfunc(attrs={}, tag=empty):
        return '<' + tag + attrlist(attrs) + '>'

    setattr(sys.modules[__name__], empty, emptyfunc)


def emptyfunc(attrs={}):
    return '<input' + attrlist(attrs) + '>'


setattr(sys.modules[__name__], 'forminput', emptyfunc)

# Declare all the non-empties
for nonempty in (
        'head',
        'body',
        'header',
        'main',
        'section',
        'article',
        'footer',
        'title',
        'div',
        'nav',
        'style',
        'script',
        'p',
        'h1',
        'h2',
        'h3',
        'h4',
        'h5',
        'h6',
        'ul',
        'ol',
        'li',
        'dl',
        'dt',
        'dd',
        'address',
        'pre',
        'blockquote',
        'a',
        'span',
        'em',
        'strong',
        'dfn',
        'code',
        'samp',
        'kbd',
        'var',
        'cite',
        'abbr',
        'acronym',
        'q',
        'sub',
        'sup',
        'tt',
        'i',
        'big',
        'small',
        'label',
        'meter',
        'form',
        'select',
        'optgroup',
        'option',
        'textarea',
        'fieldset',
        'legend',
        'button',
        'table',
        'caption',
        'thead',
        'tfoot',
        'tbody',
        'colgroup',
        'tr',
        'th',
        'td',
):

    def nonemptyfunc(clist=(), attrs={}, elem=nonempty):
        if isinstance(clist, str):
            clist = (clist, )
        return ('<' + elem + attrlist(attrs) + '>' + '\n'.join(clist) + '</' +
                elem + '>')

    setattr(sys.modules[__name__], nonempty, nonemptyfunc)
