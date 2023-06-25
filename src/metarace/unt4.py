# SPDX-License-Identifier: MIT
"""UNT4 Packet Wrapper."""

# UNT4 mode 1 constants
NUL = b'\x00'
SOH = b'\x01'
STX = b'\x02'
EOT = b'\x04'
CR = b'\x0d'
LF = b'\x0a'
ERL = b'\x0b'
ERP = b'\x0c'
DLE = b'\x10'
DC2 = b'\x12'
DC3 = b'\x13'
DC4 = b'\x14'
US = b'\x1f'

ENCMAP = {
    chr(NUL[0]): '<0>',
    chr(SOH[0]): '<O>',
    chr(STX[0]): '<T>',
    chr(EOT[0]): '<E>',
    chr(CR[0]): '<R>',
    chr(LF[0]): '<A>',
    chr(ERL[0]): '<L>',
    chr(ERP[0]): '<P>',
    chr(DLE[0]): '<D>',
    chr(DC2[0]): '<2>',
    chr(DC3[0]): '<3>',
    chr(DC4[0]): '<4>',
    chr(US[0]): '<U>'
}

TRANSMAP = str.maketrans({
    SOH[0]: 0x20,
    STX[0]: 0x20,
    EOT[0]: 0x20,
    ERL[0]: 0x20,
    ERP[0]: 0x20,
    DLE[0]: 0x20,
    DC2[0]: 0x20,
    DC3[0]: 0x20,
    DC4[0]: 0x20,
})


def encode(ubuf=''):
    """Encode the unt4 buffer for use over telegraph."""
    # escape special char
    ubuf = ubuf.replace('<', '<>')
    # escape control chars
    for key in ENCMAP:
        ubuf = ubuf.replace(key, ENCMAP[key])
    return ubuf


def decode(tbuf=''):
    """Decode the telegraph buffer to unt4 pack."""
    # decode control chars
    for key in ENCMAP:
        tbuf = tbuf.replace(ENCMAP[key], key)
    # decode special char
    tbuf = tbuf.replace('<>', '<')
    return tbuf


# UNT4 Packet class
class unt4:
    """UNT4 Packet Class."""

    def __init__(self,
                 unt4str=None,
                 prefix=None,
                 header='',
                 erp=False,
                 erl=False,
                 xx=None,
                 yy=None,
                 text=''):
        self.prefix = prefix  # <DC2>, <DC3>, etc
        self.header = header.translate(TRANSMAP)
        self.erp = erp  # true for general clearing <ERP>
        self.erl = erl  # true for <ERL>
        self.xx = xx  # input column 0-99
        self.yy = yy  # input row 0-99
        self.text = text.translate(TRANSMAP)
        if unt4str is not None:
            self.unpack(unt4str)

    def unpack(self, unt4str=''):
        """Unpack the UNT4 unicode string into this object."""
        if len(unt4str) > 2 and ord(unt4str[0]) == SOH[0] \
                            and ord(unt4str[-1]) == EOT[0]:
            self.prefix = None
            newhead = ''
            newtext = ''
            self.erl = False
            self.erp = False
            head = True  # All text before STX is considered header
            stx = False
            dle = False
            dlebuf = ''
            i = 1
            packlen = len(unt4str) - 1
            while i < packlen:
                och = ord(unt4str[i])
                if och == STX[0]:
                    stx = True
                    head = False
                elif och == DLE[0] and stx:
                    dle = True
                elif dle:
                    dlebuf += unt4str[i]
                    if len(dlebuf) == 4:
                        dle = False
                elif head:
                    if och in (DC2[0], DC3[0], DC4[0]):
                        self.prefix = och  # assume pfx before head text
                    else:
                        newhead += unt4str[i]
                elif stx:
                    if och == ERL[0]:
                        self.erl = True
                    elif och == ERP[0]:
                        self.erp = True
                    else:
                        newtext += unt4str[i]
                i += 1
            if len(dlebuf) == 4:
                self.xx = int(dlebuf[:2])
                self.yy = int(dlebuf[2:])
            self.header = newhead
            self.text = newtext

    def pack(self):
        """Return Omega Style UNT4 unicode string packet."""
        head = ''
        text = ''
        if self.erp:  # overrides any other message content
            text = chr(STX[0]) + chr(ERP[0])
        else:
            head = self.header
            if self.prefix is not None:
                head = chr(self.prefix) + head
            if self.xx is not None and self.yy is not None:
                text += chr(DLE[0]) + '{0:02d}{1:02d}'.format(
                    self.xx % 100, self.yy % 100)
            if self.text:
                text += self.text
            if self.erl:
                text += chr(ERL[0])
            if len(text) > 0:
                text = chr(STX[0]) + text
        return chr(SOH[0]) + head + text + chr(EOT[0])


# Pre-defined messages
GENERAL_CLEARING = unt4(erp=True)
GENERAL_EMPTY = unt4(xx=0, yy=0, text='')
