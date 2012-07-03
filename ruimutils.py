#!/usr/bin/env python
#fileencoding: utf-8
#Author: Liu DongMiao <liudongmiao@gmail.com>

import time
import sys

def select(pos):
    return 'a0a4 0000 02 %x (9fxx) ;; select 0x%0x' % (int(pos), int(pos))

def getaddress(addr):
    # DIGIT_MODE  1 => 0
    # NUMBER_MODE 1 => 0
    # NUM_FIELDS  8 =>
    # CHARi         =>
    chari = getchari(addr)
    num = len(chari) / 4
    bits = '00%s%s' % (binary(num, 8), chari)
    padd = (~len(bits) + 1) & 7
    bits += '0' * padd
    address = '%x' % int(bits, 2)
    if len(address) % 2 == 1:
        address = '0' + address
    return address

def getchari(addr):
    # 2.7.1.3.2.4-4 Representation of DTMF Digits
    dtmfs = {
        '1': '0001',
        '2': '0010',
        '3': '0011',
        '4': '0100',
        '5': '0101',
        '6': '0110',
        '7': '0111',
        '8': '1000',
        '9': '1001',
        '0': '1010',
        '*': '1011',
        '#': '1100',
    }
    chari = ''
    for x in str(addr):
        chari += dtmfs.get(x, '')
    return chari

def binary(data, length=0):
    return bin(int(data))[2:].zfill(length)

# CRC ITU-T
crc_itu_t_table = []
for crc in range(0, 256):
    crc <<= 8
    for x in range(0, 8):
        if crc & 0x8000:
            crc = (crc << 1 & 0xffff) ^ 0x1021
        else:
            crc <<= 1
    crc_itu_t_table.append(crc)

def crc_itu_t(data, crc=0xffff):
    for item in data:
        crc = (crc << 8 & 0xffff) ^ crc_itu_t_table[crc >> 8 & 0xff ^ item]
    return crc

def gen_crc_itu_t(data):
    check = [ord2(x) for x in data]
    return crc_itu_t(check) ^ 0xffff

def update_record(address, part, pos, value):
    data = ''

    # C.S0023 3.4.27
    # Status
    # MSG_LEN
    # SMS_MSG_TYPE
    # PARAMETER_ID
    # PARAMETER_LEN
    # Paramter Data ...

    # Status
    # XX0 -> free space
    # 001 -> read
    # 011 -> unread
    # 101 -> sent
    # 111 -> unsent
    data += '03'

    # MSG_LEN
    data += '%02x' % (len(address + value) / 2 + 25)

    # 3.4 Transport Layer Messages, Page 51
    # SMS Point-to-Point        0b00000000 => 00
    data += '00'

    # 3.4.3 Parameter Definitions, Page 53
    # Teleservice Identifier    0b00000000 => 00
    # Originating Address       0b00000010 => 02
    # Bearer data               0b00001000 => 08

    # 3.4.3.1 Teleservice Identifier, Page 54
    # Teleservice Identifier    0b00000000 => 00
    # CDMA Cellular Messaging Teleservice => 4098
    data += '00021002'  # 0x1002 = 4098

    # 3.4.3.3 Address Parameter, Page 56
    # Originating Address       0b00000010 => 02
    data += '02%02x%s' % (len(address) / 2, address)

    # 3.4.3.7 Bearer Data, Page 61
    # Bearer data               0b00001000 => 08
    data += '08%0x' % (len(value) / 2 + 16)

    # 4.5 Bearer data Subparameters, Page 87
    # Message Identifier        0b00000000 => 00
    # User Data                 0b00000001 => 01
    # Message Center Time Stamp 0b00000011 => 03
    # Message Display Mode      0b00001111 => 0F

    # 4.5.1 Message Identifier, Page 87
    # Message Identifier        0b00000000 => 00
    # MESSAGE_TYPE 4
    # 0001    => Deliver (mobile-terminated only)
    # MESSAGE_ID 16
    # 0000 0000 0000 0000
    # HEADER_IND 1
    # 0
    # RESERVED 3
    # 000
    data += '0003100000'

    # 4.5.2 User Data, Page 90
    # User Data                 0b00000001 => 01
    data += '01%02x' % (len(value) / 2 + 6)
    # MSG_ENCODING
    bits = '00000'
    # NUM_FIELDS
    bits += binary((len(value) / 2) + 4, 8)
    # padding
    bits += '000'
    data += '%04x' % int(bits, 2)
    # flash prl
    data += part
    data += '%04x' % pos
    data += '%02x' % (len(value) / 2)
    data += value

    # 4.5.4 Message Center Time Stamp, Page 93
    # Message Center Time Stamp 0b00000011 => 03
    # data += '0306%s100800' % time.strftime('%y%m%d')

    # 4.5.16 Message display mode, Page 111
    # Message Display Mode      0b00001111 => 0F
    data += '0F01D0'

    padd = 'f' * (0xff * 2 - len(data))
    apdu = 'a0dc 0104 FF %s%s (9000) ;; update %s' % (data, padd, part)
    return apdu

def update_records(mobile, data):
    address = getaddress(mobile)

    #                                   =>    27 + len(address + value) / 2
    # 0Xxx                              => 2, 25 + len(address + value) / 2
    # 00                                => 1
    # 00021002                          => 4
    # 02xxVVVVVVVV                      => 2 + len(address) / 2
    # 08xx                              => 2, 16 + len(value) / 2
    #     0003100000                    => 5
    #     01xxFFFF                      => 4, 6 + len(value) / 2
    #         PP                        => 1
    #         POSS                      => 2
    #         xxVVVVVVVV                => 1 + len(value) / 2
    #     0F01D0                        => 3

    maxvalue = 0xff - 27 - (len(address) / 2)

    values = []
    value = ''
    for x in data:
        value += '%02x' % ord2(x)
        if len(value) / 2 == maxvalue:
            values.append(value)
            value = ''
    if value:
        values.append(value)

    x = 0
    pos = 0
    count = len(values)
    cmds = []
    cmds.append('.POWER_ON')
    cmds.append(select(0x3f00))	# MF
    cmds.append(select(0x7f25))	# DF_CDMA
    cmds.append(select(0x6f3c))	# EF_SMS
    while x < count:
        part = '%01x%01x' % (x + 1, count)
        value = values[x]
        cmds.append(update_record(address, part, pos, value))
        x += 1
        pos += len(value) / 2

    cmds.append('a0dc 0104 ff 00%s (9000) ;; clear message' % ('ff' * 0xfe))
    pieces = int(len(''.join(values)) / 0x100)
    pos = 0
    cmds.append(select(0x6f30)) # EF_PRL
    for y in range(pieces+1):
        cmds.append('a0b0 %04x 80 (9000) ;; read 0x%04x' % (pos, pos))
        pos += 0x80
    cmds.append('.POWER_OFF')
    cmds.append('')
    return cmds

def ord2(x):
    if not isinstance(x, int):
        x = ord(x)
    return x

def check_data(data):
    evdo = None
    prls = []
    check = [ord2(x) for x in data]

    if crc_itu_t(check) != 0x1d0f:
        crc = (check[-2] << 8) + check[-1]
        raise SystemExit('Invalid PRL CRC: 0x%04x' % crc)

    length = (check[0] << 8) + check[1]
    if crc_itu_t(check[:length]) != 0x1d0f:
        crc = (check[length-2] << 8) + check[length-1]
        raise SystemExit('Invalid PRL1 CRC: 0x%04x' % crc)
    else:
        id1 = (check[2] << 8) + check[3]
        prls.append('%d' % id1)
        evdo = check[:length]

    check = check[length:]
    if len(check) == 0:
        return (evdo, prls)

    length = (check[0] << 8) + check[1]
    if crc_itu_t(check[:length]) != 0x1d0f:
        crc = (check[length-2] << 8) + check[length-1]
        raise SystemExit('Invalid PRL2 CRC: 0x%04x' % crc)
    else:
        id2 = (check[2] << 8) + check[3]
        prls.append('%d' % id2)
        evdo = check[:length]

    if len(check[length:]) == 2:
        return (evdo, prls)

    raise SystemExit('Invalid PRL')

if __name__ == '__main__':
    cdma = False
    name = None
    mobile = 10659165

    for name in sys.argv[1:]:
        if name.startswith('--cdma'):
            cdma = True

    if name is None:
        raise SystemExit('Usage: %s [--cdma] input.prl' % sys.argv[0])

    with open(name, 'rb') as read:
        data = read.read()

    (evdo, prls) = check_data(data)
    if cdma:
        if len(prls) > 1:
            prls.pop()
        cmds = update_records(mobile, data)
    else:
        if len(prls) > 1:
            prls.pop(0)
        cmds = update_records(mobile, evdo)

    with open('%s.cmd' % ''.join(prls), 'w') as output:
        output.write('\n'.join(cmds).upper())
        sys.stdout.write('write apdu commands to %s\n' % output.name)
