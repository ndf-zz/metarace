# SPDX-License-Identifier: MIT
"""HTML output library.

Cheap and nasty functional primitives for generating loosely
compliant HTML output. Each element primitive returns a single
escaped string.

All elements take a named parameter 'attrs' which is a dict of
key/value attributes. Non-empty elements take a parameter 'elements'
which is a list of child elements or a plain string.
"""

from xml.sax.saxutils import escape, quoteattr
import sys


class element(str):
    """String wrapper for serialised HTML text"""
    pass


def doctype():
    """HTML doctype pseudo-element"""
    return element('<!doctype html>')


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
    return element(escape(text, {'"': '&quot;'}))


def serialise(elements=()):
    """Concatenate element list into an escaped string."""
    if isinstance(elements, str):
        elements = (elements, )
    elist = []
    for j in elements:
        if type(j) is element:
            elist.append(j)
        else:
            elist.append(escapetext(j))
    return '\n'.join(elist)


def comment(elements=(' ', )):
    """Wrap elements with a comment marker"""
    text = serialise(elements).replace('<!--',
                                       '').replace('-->',
                                                   '').replace('--!>',
                                                               '').lstrip('>')
    if text.endswith('<!-'):
        text = text.rstrip('-')
    return element(''.join(('<!--', text, '-->')))


# return a valid but empty html template
def emptypage():
    return '\n'.join(
        (doctype(),
         html((
             head((
                 meta(attrs={'charset': 'utf-8'}),
                 meta(
                     attrs={
                         'name': 'viewport',
                         'content': 'width=device-width, initial-scale=1'
                     }),
                 title('__REPORT_TITLE__'),
             )),
             body((main(
                 ('__REPORT_CONTENT__', ), attrs={'class': 'container'}), ),
                  attrs={}),
         ), {'lang': 'en'})))


# Declare all the empty types
for empty in ('base', 'link', 'meta', 'hr', 'br', 'wbr', 'source', 'img',
              'embed', 'track', 'area', 'col', 'param', 'hr', 'br', 'img',
              'col'):

    def emptyfunc(attrs={}, tag=empty):
        return element(''.join(('<', tag, attrlist(attrs), '>')))

    setattr(sys.modules[__name__], empty, emptyfunc)


def forminput(attrs={}):
    return element(''.join(('<input', attrlist(attrs), '>')))


# Declare all the non-empty elements (except specials defined above)
for nonempty in (
        'html',
        'head',
        'title',
        'style',
        'body',
        'article',
        'section',
        'nav',
        'aside',
        'h1',
        'h2',
        'h3',
        'h4',
        'h5',
        'h6',
        'hgroup',
        'header',
        'footer',
        'address',
        'p',
        'pre',
        'blockquote',
        'ol',
        'ul',
        'menu',
        'li',
        'dl',
        'dt',
        'dd',
        'figure',
        'figcaption',
        'main',
        'div',
        'a',
        'em',
        'strong',
        'small',
        's',
        'cite',
        'q',
        'dfn',
        'abbr',
        'ruby',
        'rt',
        'rp',
        'data',
        'time',
        'code',
        'var',
        'samp',
        'kbd',
        'sub',
        'sup',
        'i',
        'b',
        'u',
        'mark',
        'bdi',
        'bdo',
        'span',
        'ins',
        'del',
        'picture',
        'object',
        'video',
        'audio',
        'map',
        'math',
        'svg',
        'table',
        'caption',
        'colgroup',
        'tbody',
        'thead',
        'tfoot',
        'tr',
        'td',
        'th',
        'form',
        'label',
        'button',
        'select',
        'datalist',
        'optgroup',
        'option',
        'textarea',
        'output',
        'progress',
        'meter',
        'fieldset',
        'legend',
        'details',
        'summary',
        'dialog',
        'script',
        'slot',
        'canvas',
):

    def nonemptyfunc(elements=(), attrs={}, elem=nonempty):
        return element(''.join(('<', elem, attrlist(attrs), '>',
                                serialise(elements), '</', elem, '>')))

    setattr(sys.modules[__name__], nonempty, nonemptyfunc)
