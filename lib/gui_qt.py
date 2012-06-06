#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@gitorious
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import sys, time, datetime, re
from i18n import _

try:
    import PyQt4
except:
    print "could not import PyQt4"
    print "on Linux systems, you may try 'sudo apt-get install python-qt4'"
    sys.exit(1)

from PyQt4.QtGui import *
from PyQt4.QtCore import *
import PyQt4.QtCore as QtCore
import PyQt4.QtGui as QtGui
from interface import DEFAULT_SERVERS

try:
    import icons_rc
except:
    print "Could not import icons_rp.py"
    print "Please generate it with: 'pyrcc4 icons.qrc -o icons_rc.py'"
    sys.exit(1)

from wallet import format_satoshis
import bmp, mnemonic, pyqrnative

from decimal import Decimal

import platform
MONOSPACE_FONT = 'Lucida Console' if platform.system() == 'Windows' else 'monospace'
    

def numbify(entry, is_int = False):
    text = unicode(entry.text()).strip()
    chars = '0123456789'
    if not is_int: chars +='.'
    s = ''.join([i for i in text if i in chars])
    if not is_int:
        if '.' in s:
            p = s.find('.')
            s = s.replace('.','')
            s = s[:p] + '.' + s[p:p+8]
        try:
            amount = int( Decimal(s) * 100000000 )
        except:
            amount = None
    else:
        try:
            amount = int( s )
        except:
            amount = None
    entry.setText(s)
    return amount


class Timer(QtCore.QThread):
    def run(self):
        while True:
            self.emit(QtCore.SIGNAL('timersignal'))
            time.sleep(0.5)

class EnterButton(QPushButton):
    def __init__(self, text, func):
        QPushButton.__init__(self, text)
        self.func = func
        self.clicked.connect(func)

    def keyPressEvent(self, e):
        if e.key() == QtCore.Qt.Key_Return:
            apply(self.func,())

class StatusBarButton(QPushButton):
    def __init__(self, icon, tooltip, func):
        QPushButton.__init__(self, icon, '')
        self.setToolTip(tooltip)
        self.setFlat(True)
        self.setMaximumWidth(25)
        self.clicked.connect(func)
        self.func = func

    def keyPressEvent(self, e):
        if e.key() == QtCore.Qt.Key_Return:
            apply(self.func,())


class QRCodeWidget(QWidget):

    def __init__(self, addr):
        super(QRCodeWidget, self).__init__()
        self.setGeometry(300, 300, 350, 350)
        self.set_addr(addr)

    def set_addr(self, addr):
        self.addr = addr
        self.qr = pyqrnative.QRCode(4, pyqrnative.QRErrorCorrectLevel.L)
        self.qr.addData(addr)
        self.qr.make()
        
    def paintEvent(self, e):
        qp = QtGui.QPainter()
        qp.begin(self)
        boxsize = 7
        size = self.qr.getModuleCount()*boxsize
        k = self.qr.getModuleCount()
        black = QColor(0, 0, 0, 255)
        white = QColor(255, 255, 255, 255)
        for r in range(k):
            for c in range(k):
                if self.qr.isDark(r, c):
                    qp.setBrush(black)
                    qp.setPen(black)
                else:
                    qp.setBrush(white)
                    qp.setPen(white)
                qp.drawRect(c*boxsize, r*boxsize, boxsize, boxsize)
        qp.end()
        


def ok_cancel_buttons(dialog):
    hbox = QHBoxLayout()
    hbox.addStretch(1)
    b = QPushButton("OK")
    hbox.addWidget(b)
    b.clicked.connect(dialog.accept)
    b = QPushButton("Cancel")
    hbox.addWidget(b)
    b.clicked.connect(dialog.reject)
    return hbox


class ElectrumWindow(QMainWindow):

    def __init__(self, wallet):
        QMainWindow.__init__(self)
        self.wallet = wallet
        self.wallet.gui_callback = self.update_callback

        self.funds_error = False

        self.tabs = tabs = QTabWidget(self)
        tabs.addTab(self.create_history_tab(), _('History') )
        if self.wallet.seed:
            tabs.addTab(self.create_send_tab(), _('Send') )
        tabs.addTab(self.create_receive_tab(), _('Receive') )
        tabs.addTab(self.create_change_tab(), _('Change') )
        tabs.addTab(self.create_contacts_tab(), _('Contacts') )
        tabs.addTab(self.create_wall_tab(), _('Wall') )
        tabs.setMinimumSize(600, 400)
        tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCentralWidget(tabs)
        self.create_status_bar()
        self.setGeometry(100,100,840,400)
        title = 'Electrum ' + self.wallet.electrum_version + '  -  ' + self.wallet.path
        if not self.wallet.seed: title += ' [seedless]'
        self.setWindowTitle( title )
        self.show()

        QShortcut(QKeySequence("Ctrl+W"), self, self.close)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)
        QShortcut(QKeySequence("Ctrl+PgUp"), self, lambda: tabs.setCurrentIndex( (tabs.currentIndex() - 1 )%tabs.count() ))
        QShortcut(QKeySequence("Ctrl+PgDown"), self, lambda: tabs.setCurrentIndex( (tabs.currentIndex() + 1 )%tabs.count() ))
        
        self.connect(self, QtCore.SIGNAL('updatesignal'), self.update_wallet)


    def connect_slots(self, sender):
        if self.wallet.seed:
            self.connect(sender, QtCore.SIGNAL('timersignal'), self.check_recipient)
            self.previous_payto_e=''

    def check_recipient(self):
        if self.payto_e.hasFocus():
            return
        r = unicode( self.payto_e.text() )
        if r != self.previous_payto_e:
            self.previous_payto_e = r
            r = r.strip()
            if re.match('^(|([\w\-\.]+)@)((\w[\w\-]+\.)+[\w\-]+)$', r):
                try:
                    to_address = self.wallet.get_alias(r, True, self.show_message, self.question)
                except:
                    return
                if to_address:
                    s = r + ' <' + to_address + '>'
                    self.payto_e.setText(s)


    def update_callback(self):
        self.emit(QtCore.SIGNAL('updatesignal'))

    def update_wallet(self):
        if self.wallet.interface and self.wallet.interface.is_connected:
            if self.wallet.blocks == -1:
                text = _( "Connecting..." )
                icon = QIcon(":icons/status_disconnected.png")
            elif self.wallet.blocks == 0:
                text = _( "Server not ready" )
                icon = QIcon(":icons/status_disconnected.png")
            elif not self.wallet.up_to_date:
                text = _( "Synchronizing..." )
                icon = QIcon(":icons/status_waiting.png")
            else:
                c, u = self.wallet.get_balance()
                text =  _( "Balance" ) + ": %s "%( format_satoshis(c,False,self.wallet.num_zeros) )
                if u: text +=  "[%s unconfirmed]"%( format_satoshis(u,True,self.wallet.num_zeros).strip() )
                icon = QIcon(":icons/status_connected.png")
        else:
            text = _( "Not connected" )
            icon = QIcon(":icons/status_disconnected.png")

        if self.funds_error:
            text = _( "Not enough funds" )

        self.statusBar().showMessage(text)
        self.status_button.setIcon( icon )

        if self.wallet.up_to_date:
            self.textbox.setText( self.wallet.banner )
            self.update_history_tab()
            self.update_receive_tab()
            self.update_contacts_tab()


    def create_history_tab(self):
        self.history_list = w = QTreeWidget(self)
        #print w.getContentsMargins()
        w.setColumnCount(5)
        w.setColumnWidth(0, 40) 
        w.setColumnWidth(1, 140) 
        w.setColumnWidth(2, 350) 
        w.setColumnWidth(3, 140) 
        w.setColumnWidth(4, 140) 
        w.setHeaderLabels( [ '', _( 'Date' ), _( 'Description' ) , _('Amount'), _('Balance')] )
        self.connect(w, SIGNAL('itemActivated(QTreeWidgetItem*, int)'), self.tx_details)
        self.connect(w, SIGNAL('itemDoubleClicked(QTreeWidgetItem*, int)'), self.tx_label_clicked)
        self.connect(w, SIGNAL('itemChanged(QTreeWidgetItem*, int)'), self.tx_label_changed)
        return w

    def tx_details(self, item, column):
        tx_hash = str(item.toolTip(0))
        tx = self.wallet.tx_history.get(tx_hash)

        if tx['height']:
            conf = self.wallet.blocks - tx['height'] + 1
            time_str = datetime.datetime.fromtimestamp( tx['timestamp']).isoformat(' ')[:-3]
        else:
            conf = 0
            time_str = 'pending'

        tx_details = _("Transaction Details") +"\n\n" \
            + "Transaction ID:\n" + tx_hash + "\n\n" \
            + "Status: %d confirmations\n\n"%conf  \
            + "Date: %s\n\n"%time_str \
            + "Inputs:\n-"+ '\n-'.join(tx['inputs']) + "\n\n" \
            + "Outputs:\n-"+ '\n-'.join(tx['outputs'])

        r = self.wallet.receipts.get(tx_hash)
        if r:
            tx_details += "\n_______________________________________" \
                + '\n\nSigned URI: ' + r[2] \
                + "\n\nSigned by: " + r[0] \
                + '\n\nSignature: ' + r[1]

        QMessageBox.information(self, 'Details', tx_details, 'OK')


    def tx_label_clicked(self, item, column):
        if column==2 and item.isSelected():
            tx_hash = str(item.toolTip(0))
            self.is_edit=True
            #if not self.wallet.labels.get(tx_hash): item.setText(2,'')
            item.setFlags(Qt.ItemIsEditable|Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            self.history_list.editItem( item, column )
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            self.is_edit=False

    def tx_label_changed(self, item, column):
        if self.is_edit: 
            return
        self.is_edit=True
        tx_hash = str(item.toolTip(0))
        tx = self.wallet.tx_history.get(tx_hash)
        s = self.wallet.labels.get(tx_hash)
        text = unicode( item.text(2) )
        if text: 
            self.wallet.labels[tx_hash] = text
            item.setForeground(2, QBrush(QColor('black')))
        else:
            if s: self.wallet.labels.pop(tx_hash)
            text = tx['default_label']
            item.setText(2, text)
            item.setForeground(2, QBrush(QColor('gray')))
        self.is_edit=False

    def address_label_clicked(self, item, column, l):
        if column==1 and item.isSelected():
            addr = unicode( item.text(0) )
            if addr in map(lambda x:x[1], self.wallet.aliases.values()):
                return
            item.setFlags(Qt.ItemIsEditable|Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            l.editItem( item, column )
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)

    def address_label_changed(self, item, column, l):
        addr = unicode( item.text(0) )
        text = unicode( item.text(1) )
        if text:
            self.wallet.labels[addr] = text
        else:
            s = self.wallet.labels.get(addr)
            if s: self.wallet.labels.pop(addr)
        self.update_history_tab()

    def update_history_tab(self):
        self.history_list.clear()
        balance = 0
        for tx in self.wallet.get_tx_history():
            tx_hash = tx['tx_hash']
            if tx['height']:
                conf = self.wallet.blocks - tx['height'] + 1
                time_str = datetime.datetime.fromtimestamp( tx['timestamp']).isoformat(' ')[:-3]
                icon = QIcon(":icons/confirmed.png")
            else:
                conf = 0
                time_str = 'pending'
                icon = QIcon(":icons/unconfirmed.png")
            v = tx['value']
            balance += v 
            label = self.wallet.labels.get(tx_hash)
            is_default_label = (label == '') or (label is None)
            if is_default_label: label = tx['default_label']

            item = QTreeWidgetItem( [ '', time_str, label, format_satoshis(v,True,self.wallet.num_zeros), format_satoshis(balance,False,self.wallet.num_zeros)] )
            item.setFont(2, QFont(MONOSPACE_FONT))
            item.setFont(3, QFont(MONOSPACE_FONT))
            item.setFont(4, QFont(MONOSPACE_FONT))
            item.setToolTip(0, tx_hash)
            if is_default_label:
                item.setForeground(2, QBrush(QColor('grey')))

            item.setIcon(0, icon)
            self.history_list.insertTopLevelItem(0,item)


    def create_send_tab(self):
        w = QWidget()

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnMinimumWidth(3,300)
        grid.setColumnStretch(4,1)

        self.payto_e = QLineEdit()
        grid.addWidget(QLabel(_('Pay to')), 1, 0)
        grid.addWidget(self.payto_e, 1, 1, 1, 3)

        self.message_e = QLineEdit()
        grid.addWidget(QLabel(_('Description')), 2, 0)
        grid.addWidget(self.message_e, 2, 1, 1, 3)

        self.amount_e = QLineEdit()
        grid.addWidget(QLabel(_('Amount')), 3, 0)
        grid.addWidget(self.amount_e, 3, 1, 1, 2)
        
        self.fee_e = QLineEdit()
        grid.addWidget(QLabel(_('Fee')), 4, 0)
        grid.addWidget(self.fee_e, 4, 1, 1, 2)
        
        b = EnterButton(_("Send"), self.do_send)
        grid.addWidget(b, 5, 1)

        b = EnterButton(_("Clear"),self.do_clear)
        grid.addWidget(b, 5, 2)

        self.payto_sig = QLabel('')
        grid.addWidget(self.payto_sig, 6, 0, 1, 4)

        w.setLayout(grid) 
        w.show()

        w2 = QWidget()
        vbox = QVBoxLayout()
        vbox.addWidget(w)
        vbox.addStretch(1)
        w2.setLayout(vbox)

        def entry_changed( is_fee ):
            self.funds_error = False
            amount = numbify(self.amount_e)
            fee = numbify(self.fee_e)
            if not is_fee: fee = None
            if amount is None:
                return
            inputs, total, fee = self.wallet.choose_tx_inputs( amount, fee )
            if not is_fee:
                self.fee_e.setText( str( Decimal( fee ) / 100000000 ) )
            if inputs:
                palette = QPalette()
                palette.setColor(self.amount_e.foregroundRole(), QColor('black'))
            else:
                palette = QPalette()
                palette.setColor(self.amount_e.foregroundRole(), QColor('red'))
                self.funds_error = True
            self.amount_e.setPalette(palette)
            self.fee_e.setPalette(palette)

        self.amount_e.textChanged.connect(lambda: entry_changed(False) )
        self.fee_e.textChanged.connect(lambda: entry_changed(True) )

        return w2

    def do_send(self):

        label = unicode( self.message_e.text() )
        r = unicode( self.payto_e.text() )
        r = r.strip()

        m1 = re.match('^(|([\w\-\.]+)@)((\w[\w\-]+\.)+[\w\-]+)$', r)
        m2 = re.match('(|([\w\-\.]+)@)((\w[\w\-]+\.)+[\w\-]+) \<([1-9A-HJ-NP-Za-km-z]{26,})\>', r)
        
        if m1:
            to_address = self.wallet.get_alias(r, True, self.show_message, self.question)
            if not to_address:
                return
        elif m2:
            to_address = m2.group(5)
        else:
            to_address = r

        if not self.wallet.is_valid(to_address):
            QMessageBox.warning(self, _('Error'), _('Invalid Bitcoin Address') + ':\n' + to_address, _('OK'))
            return

        try:
            amount = int( Decimal( unicode( self.amount_e.text())) * 100000000 )
        except:
            QMessageBox.warning(self, _('Error'), _('Invalid Amount'), _('OK'))
            return
        try:
            fee = int( Decimal( unicode( self.fee_e.text())) * 100000000 )
        except:
            QMessageBox.warning(self, _('Error'), _('Invalid Fee'), _('OK'))
            return

        if self.wallet.use_encryption:
            password = self.password_dialog()
            if not password:
                return
        else:
            password = None

        try:
            tx = self.wallet.mktx( to_address, amount, label, password, fee )
        except BaseException, e:
            self.show_message(str(e))
            return
            
        status, msg = self.wallet.sendtx( tx )
        if status:
            QMessageBox.information(self, '', _('Payment sent.')+'\n'+msg, _('OK'))
            self.do_clear()
            self.update_contacts_tab()
        else:
            QMessageBox.warning(self, _('Error'), msg, _('OK'))


    def set_url(self, url):
        payto, amount, label, message, signature, identity, url = self.wallet.parse_url(url, self.show_message, self.question)
        self.tabs.setCurrentIndex(1)
        self.payto_e.setText(payto)
        self.message_e.setText(message)
        self.amount_e.setText(amount)
        if identity:
            self.set_frozen(self.payto_e,True)
            self.set_frozen(self.amount_e,True)
            self.set_frozen(self.message_e,True)
            self.payto_sig.setText( '      The bitcoin URI was signed by ' + identity )
        else:
            self.payto_sig.setVisible(False)

    def do_clear(self):
        self.payto_sig.setVisible(False)
        for e in [self.payto_e, self.message_e, self.amount_e, self.fee_e]:
            e.setText('')
            self.set_frozen(e,False)

    def set_frozen(self,entry,frozen):
        if frozen:
            entry.setReadOnly(True)
            entry.setFrame(False)
            palette = QPalette()
            palette.setColor(entry.backgroundRole(), QColor('lightgray'))
            entry.setPalette(palette)
        else:
            entry.setReadOnly(False)
            entry.setFrame(True)
            palette = QPalette()
            palette.setColor(entry.backgroundRole(), QColor('white'))
            entry.setPalette(palette)


    def get_current_addr(self, is_recv):
        if is_recv:
            l = self.receive_list
        else:
            l = self.contacts_list
        i = l.currentItem()
        if i: 
            return unicode( i.text(0) )
        else:
            return ''


    def add_receive_buttons(self):

        l = self.receive_list
        hbox = self.receive_buttons_hbox
        def create_new_address():
            if self.question( _("Warning:\nThis will create an address beyond your current gap limit.") + "\n" + _("Are you sure?")):
                self.wallet.create_new_address(False)
                self.update_receive_tab()
            
        hbox.addWidget(EnterButton(_("New"),create_new_address))
        hbox.addWidget(EnterButton(_("QR"),lambda: self.show_address_qrcode(self.get_current_addr(True))))
        hbox.addWidget(EnterButton(_("Copy to Clipboard"), lambda: self.app.clipboard().setText(self.get_current_addr(True))))

        def toggle_freeze():
            addr = self.get_current_addr(True)
            if not addr: return
            if addr in self.wallet.frozen_addresses:
                self.wallet.frozen_addresses.remove(addr)
            else:
                self.wallet.frozen_addresses.append(addr)
            self.wallet.save()
            self.update_receive_tab()

        self.freezeButton = b = EnterButton(_("Freeze"), toggle_freeze)
        hbox.addWidget(b)

        def toggle_priority():
            addr = self.get_current_addr(True)
            if not addr: return
            if addr in self.wallet.prioritized_addresses:
                self.wallet.prioritized_addresses.remove(addr)
            else:
                self.wallet.prioritized_addresses.append(addr)
            self.wallet.save()
            self.update_receive_tab()

        self.prioritizeButton = b = EnterButton(_("Set priority"), toggle_priority)
        hbox.addWidget(b)
        hbox.addStretch(1)


    def add_contacts_buttons(self):
        l = self.contacts_list
        hbox = self.contacts_buttons_hbox

        hbox.addWidget(EnterButton(_("QR"),lambda: self.show_address_qrcode(self.get_current_addr(False))))
        hbox.addWidget(EnterButton(_("Copy to Clipboard"), lambda: self.app.clipboard().setText(self.get_current_addr(False))))
        def payto():
            addr = self.get_current_addr(False)
            if not addr:return
            self.tabs.setCurrentIndex(1)
            self.payto_e.setText(addr)
            self.amount_e.setFocus()
        hbox.addWidget(EnterButton(_('Pay to'), lambda: payto()))
        hbox.addWidget(EnterButton(_("New"), self.newaddress_dialog))
        hbox.addStretch(1)

    def update_receive_buttons(self):
        addr = self.get_current_addr(True)
        t = _("Unfreeze") if addr in self.wallet.frozen_addresses else _("Freeze")
        self.freezeButton.setText(t)

        t = _("Remove priority") if addr in self.wallet.prioritized_addresses else _("Set priority")
        self.prioritizeButton.setText(t)

    
    def create_list_tab(self, headers):
        "generic tab creatino method"
        l = QTreeWidget(self)
        l.setColumnCount( len(headers) )
        l.setColumnWidth(0, 350) 
        l.setColumnWidth(1, 330)
        l.setColumnWidth(2, 100) 
        l.setColumnWidth(3, 10) 
        l.setHeaderLabels( headers )

        w = QWidget()
        vbox = QVBoxLayout()
        w.setLayout(vbox)

        vbox.setMargin(0)
        vbox.setSpacing(0)
        vbox.addWidget(l)
        buttons = QWidget()
        vbox.addWidget(buttons)

        hbox = QHBoxLayout()
        hbox.setMargin(0)
        hbox.setSpacing(0)
        buttons.setLayout(hbox)

        self.connect(l, SIGNAL('itemDoubleClicked(QTreeWidgetItem*, int)'), lambda a, b: self.address_label_clicked(a,b,l))
        self.connect(l, SIGNAL('itemChanged(QTreeWidgetItem*, int)'), lambda a,b: self.address_label_changed(a,b,l))
        return l,w,hbox

    def create_receive_tab(self):
        l,w,hbox = self.create_list_tab([_('Address'), _('Label'), _('Balance'), _('Tx')])
        l.selectionModel().currentChanged.connect(self.update_receive_buttons)
        self.receive_list = l
        self.receive_buttons_hbox = hbox
        self.add_receive_buttons()
        return w

    def create_change_tab(self):
        l,w,hbox = self.create_list_tab([_('Address'), _('Label'), _('Balance'), _('Tx')])
        self.change_list = l
        return w

    def create_contacts_tab(self):
        l,w,hbox = self.create_list_tab([_('Address'), _('Label'), _('Tx')])
        self.connect(l, SIGNAL('itemActivated(QTreeWidgetItem*, int)'), self.show_contact_details)
        self.contacts_list = l
        self.contacts_buttons_hbox = hbox
        self.add_contacts_buttons()
        return w

    def update_receive_tab(self):
        self.receive_list.clear()
        self.change_list.clear()
        gap = 0
        is_red = False
        for address in self.wallet.all_addresses():
            if self.wallet.is_change(address):
                l = self.change_list
            else:
                l = self.receive_list

            label = self.wallet.labels.get(address,'')
            n = 0 
            h = self.wallet.history.get(address,[])
            for item in h:
                if not item['is_input'] : n=n+1

            if n==0:
                tx = "None"
                if address in self.wallet.addresses:
                    gap += 1
                    if gap > self.wallet.gap_limit:
                        is_red = True
            else:
                tx = "%d"%n
                if address in self.wallet.addresses:
                    gap = 0

            c, u = self.wallet.get_addr_balance(address)
            balance = format_satoshis( c + u, False, self.wallet.num_zeros )
            item = QTreeWidgetItem( [ address, label, balance, tx] )
            if address in self.wallet.frozen_addresses: 
                item.setBackgroundColor(0, QColor('lightblue'))
            elif address in self.wallet.prioritized_addresses: 
                item.setBackgroundColor(0, QColor('lightgreen'))

            item.setFont(0, QFont(MONOSPACE_FONT))
            if is_red and address in self.wallet.addresses:
                item.setBackgroundColor(0, QColor('red'))

            l.addTopLevelItem(item)

    def show_contact_details(self, item, column):
        m = unicode(item.text(0))
        a = self.wallet.aliases.get(m)
        if a:
            if a[0] in self.wallet.authorities.keys():
                s = self.wallet.authorities.get(a[0])
            else:
                s = "self-signed"
            msg = 'Alias: '+ m + '\nTarget address: '+ a[1] + '\n\nSigned by: ' + s + '\nSigning address:' + a[0]
            QMessageBox.information(self, 'Alias', msg, 'OK')

    def update_contacts_tab(self):
        self.contacts_list.clear()

        for alias, v in self.wallet.aliases.items():
            s, target = v
            item = QTreeWidgetItem( [ target, alias, '-'] )
            self.contacts_list.addTopLevelItem(item)
            
        for address in self.wallet.addressbook:
            label = self.wallet.labels.get(address,'')
            n = 0 
            for item in self.wallet.tx_history.values():
                if address in item['outputs'] : n=n+1
            tx = "None" if n==0 else "%d"%n
            item = QTreeWidgetItem( [ address, label, tx] )
            item.setFont(0, QFont(MONOSPACE_FONT))
            self.contacts_list.addTopLevelItem(item)


    def create_wall_tab(self):
        self.textbox = textbox = QTextEdit(self)
        textbox.setFont(QFont(MONOSPACE_FONT))
        textbox.setReadOnly(True)
        return textbox

    def create_status_bar(self):
        sb = QStatusBar()
        sb.setFixedHeight(35)
        if self.wallet.seed:
            sb.addPermanentWidget( StatusBarButton( QIcon(":icons/lock.png"), "Password", lambda: self.change_password_dialog(self.wallet, self) ) )
        sb.addPermanentWidget( StatusBarButton( QIcon(":icons/preferences.png"), "Preferences", self.settings_dialog ) )
        if self.wallet.seed:
            sb.addPermanentWidget( StatusBarButton( QIcon(":icons/seed.png"), "Seed", lambda: self.show_seed_dialog(self.wallet, self) ) )
        self.status_button = StatusBarButton( QIcon(":icons/status_disconnected.png"), "Network", lambda: self.network_dialog(self.wallet, self) ) 
        sb.addPermanentWidget( self.status_button )
        self.setStatusBar(sb)

    def newaddress_dialog(self):
        text, ok = QInputDialog.getText(self, _('New Contact'), _('Address') + ':')
        address = unicode(text)
        if ok:
            if self.wallet.is_valid(address):
                self.wallet.addressbook.append(address)
                self.wallet.save()
                self.update_contacts_tab()
            else:
                QMessageBox.warning(self, _('Error'), _('Invalid Address'), _('OK'))

    @staticmethod
    def show_seed_dialog(wallet, parent=None):

        if not wallet.seed:
            QMessageBox.information(parent, _('Message'), _('No seed'), _('OK'))
            return

        if wallet.use_encryption:
            password = parent.password_dialog()
            if not password: return
        else:
            password = None
            
        try:
            seed = wallet.pw_decode( wallet.seed, password)
        except:
            QMessageBox.warning(parent, _('Error'), _('Incorrect Password'), _('OK'))
            return

        msg = _("Your wallet generation seed is") + ":\n\n" + seed + "\n\n"\
              + _("Please keep it in a safe place; if you lose it, you will not be able to restore your wallet.") + "\n\n" \
              + _("Equivalently, your wallet seed can be stored and recovered with the following mnemonic code") + ":\n\n\"" \
              + ' '.join(mnemonic.mn_encode(seed)) + "\"\n\n\n"

        d = QDialog(None)
        d.setModal(1)
        d.setWindowTitle(_("Seed"))
        d.setMinimumSize(400, 270)

        vbox = QVBoxLayout()
        hbox = QHBoxLayout()
        vbox2 = QVBoxLayout()
        l = QLabel()
        l.setPixmap(QPixmap(":icons/seed.png").scaledToWidth(56))
        vbox2.addWidget(l)
        vbox2.addStretch(1)
        hbox.addLayout(vbox2)
        hbox.addWidget(QLabel(msg))
        vbox.addLayout(hbox)

        hbox = QHBoxLayout()
        hbox.addStretch(1)


        if parent:
            app = parent.app
        else:
            app = QApplication

        b = QPushButton(_("Copy to Clipboard"))
        b.clicked.connect(lambda: app.clipboard().setText(seed + ' "' + ' '.join(mnemonic.mn_encode(seed))+'"'))
        hbox.addWidget(b)
        b = QPushButton(_("View as QR Code"))
        b.clicked.connect(lambda: ElectrumWindow.show_seed_qrcode(seed))
        hbox.addWidget(b)

        b = QPushButton(_("OK"))
        b.clicked.connect(d.accept)
        hbox.addWidget(b)
        vbox.addLayout(hbox)
        d.setLayout(vbox)
        d.exec_()

    @staticmethod
    def show_seed_qrcode(seed):
        if not seed: return
        d = QDialog(None)
        d.setModal(1)
        d.setWindowTitle(_("Seed"))
        d.setMinimumSize(270, 300)
        vbox = QVBoxLayout()
        vbox.addWidget(QRCodeWidget(seed))
        hbox = QHBoxLayout()
        hbox.addStretch(1)
        b = QPushButton(_("OK"))
        hbox.addWidget(b)
        b.clicked.connect(d.accept)

        vbox.addLayout(hbox)
        d.setLayout(vbox)
        d.exec_()

    def show_address_qrcode(self,address):
        if not address: return
        d = QDialog(None)
        d.setModal(1)
        d.setWindowTitle(address)
        d.setMinimumSize(270, 350)
        vbox = QVBoxLayout()
        qrw = QRCodeWidget(address)
        vbox.addWidget(qrw)

        hbox = QHBoxLayout()
        amount_e = QLineEdit()
        hbox.addWidget(QLabel(_('Amount')))
        hbox.addWidget(amount_e)
        vbox.addLayout(hbox)

        #hbox = QHBoxLayout()
        #label_e = QLineEdit()
        #hbox.addWidget(QLabel('Label'))
        #hbox.addWidget(label_e)
        #vbox.addLayout(hbox)

        def amount_changed():
            amount = numbify(amount_e)
            #label = str( label_e.getText() )
            if amount is not None:
                qrw.set_addr('bitcoin:%s?amount=%s'%(address,str( Decimal(amount) /100000000)))
            else:
                qrw.set_addr( address )
            qrw.repaint()

        def do_save():
            bmp.save_qrcode(qrw.qr, "qrcode.bmp")
            self.show_message(_("QR code saved to file") + " 'qrcode.bmp'")
            
        amount_e.textChanged.connect( amount_changed )

        hbox = QHBoxLayout()
        hbox.addStretch(1)
        b = QPushButton(_("Save"))
        b.clicked.connect(do_save)
        hbox.addWidget(b)
        b = QPushButton(_("Close"))
        hbox.addWidget(b)
        b.clicked.connect(d.accept)

        vbox.addLayout(hbox)
        d.setLayout(vbox)
        d.exec_()

    def question(self, msg):
        return QMessageBox.question(self, _('Message'), msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def show_message(self, msg):
        QMessageBox.information(self, _('Message'), msg, _('OK'))

    def password_dialog(self ):
        d = QDialog(self)
        d.setModal(1)

        pw = QLineEdit()
        pw.setEchoMode(2)

        vbox = QVBoxLayout()
        msg = _('Please enter your password')
        vbox.addWidget(QLabel(msg))

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.addWidget(QLabel(_('Password')), 1, 0)
        grid.addWidget(pw, 1, 1)
        vbox.addLayout(grid)

        vbox.addLayout(ok_cancel_buttons(d))
        d.setLayout(vbox) 

        if not d.exec_(): return
        return unicode(pw.text())

    @staticmethod
    def change_password_dialog( wallet, parent=None ):

        if not wallet.seed:
            QMessageBox.information(parent, _('Error'), _('No seed'), _('OK'))
            return

        d = QDialog(parent)
        d.setModal(1)

        pw = QLineEdit()
        pw.setEchoMode(2)
        new_pw = QLineEdit()
        new_pw.setEchoMode(2)
        conf_pw = QLineEdit()
        conf_pw.setEchoMode(2)

        vbox = QVBoxLayout()
        if parent:
            msg = (_('Your wallet is encrypted. Use this dialog to change your password.')+'\n'+_('To disable wallet encryption, enter an empty new password.')) if wallet.use_encryption else _('Your wallet keys are not encrypted')
        else:
            msg = _("Please choose a password to encrypt your wallet keys.")+'\n'+_("Leave these fields empty if you want to disable encryption.")
        vbox.addWidget(QLabel(msg))

        grid = QGridLayout()
        grid.setSpacing(8)

        if wallet.use_encryption:
            grid.addWidget(QLabel(_('Password')), 1, 0)
            grid.addWidget(pw, 1, 1)

        grid.addWidget(QLabel(_('New Password')), 2, 0)
        grid.addWidget(new_pw, 2, 1)

        grid.addWidget(QLabel(_('Confirm Password')), 3, 0)
        grid.addWidget(conf_pw, 3, 1)
        vbox.addLayout(grid)

        vbox.addLayout(ok_cancel_buttons(d))
        d.setLayout(vbox) 

        if not d.exec_(): return

        password = unicode(pw.text()) if wallet.use_encryption else None
        new_password = unicode(new_pw.text())
        new_password2 = unicode(conf_pw.text())

        try:
            seed = wallet.pw_decode( wallet.seed, password)
        except:
            QMessageBox.warning(parent, _('Error'), _('Incorrect Password'), _('OK'))
            return

        if new_password != new_password2:
            QMessageBox.warning(parent, _('Error'), _('Passwords do not match'), _('OK'))
            return

        wallet.update_password(seed, password, new_password)

    @staticmethod
    def seed_dialog(wallet, parent=None):
        d = QDialog(parent)
        d.setModal(1)

        vbox = QVBoxLayout()
        msg = _("Please enter your wallet seed or the corresponding mnemonic list of words, and the gap limit of your wallet.")
        vbox.addWidget(QLabel(msg))

        grid = QGridLayout()
        grid.setSpacing(8)

        seed_e = QLineEdit()
        grid.addWidget(QLabel(_('Seed or mnemonic')), 1, 0)
        grid.addWidget(seed_e, 1, 1)

        gap_e = QLineEdit()
        gap_e.setText("5")
        grid.addWidget(QLabel(_('Gap limit')), 2, 0)
        grid.addWidget(gap_e, 2, 1)
        gap_e.textChanged.connect(lambda: numbify(gap_e,True))
        vbox.addLayout(grid)

        vbox.addLayout(ok_cancel_buttons(d))
        d.setLayout(vbox) 

        if not d.exec_(): return

        try:
            gap = int(unicode(gap_e.text()))
        except:
            QMessageBox.warning(None, _('Error'), 'error', 'OK')
            sys.exit(0)

        try:
            seed = unicode(seed_e.text())
            seed.decode('hex')
        except:
            print "not hex, trying decode"
            try:
                seed = mnemonic.mn_decode( seed.split(' ') )
            except:
                QMessageBox.warning(None, _('Error'), _('I cannot decode this'), _('OK'))
                sys.exit(0)
        if not seed:
            QMessageBox.warning(None, _('Error'), _('No seed'), 'OK')
            sys.exit(0)
        
        wallet.seed = str(seed)
        #print repr(wallet.seed)
        wallet.gap_limit = gap
        return True


    def settings_dialog(self):
        d = QDialog(self)
        d.setModal(1)

        vbox = QVBoxLayout()

        msg = _('Here are the settings of your wallet.')
        vbox.addWidget(QLabel(msg))

        grid = QGridLayout()
        grid.setSpacing(8)
        vbox.addLayout(grid)

        fee_e = QLineEdit()
        fee_e.setText("%s"% str( Decimal( self.wallet.fee)/100000000 ) )
        grid.addWidget(QLabel(_('Fee per tx. input')), 2, 0)
        grid.addWidget(fee_e, 2, 1)
        fee_e.textChanged.connect(lambda: numbify(fee_e,False))

        nz_e = QLineEdit()
        nz_e.setText("%d"% self.wallet.num_zeros)
        grid.addWidget(QLabel(_('Zeros displayed after decimal point')), 3, 0)
        grid.addWidget(nz_e, 3, 1)
        nz_e.textChanged.connect(lambda: numbify(nz_e,True))

        vbox.addLayout(ok_cancel_buttons(d))
        d.setLayout(vbox) 

        if not d.exec_(): return

        fee = unicode(fee_e.text())
        try:
            fee = int( 100000000 * Decimal(fee) )
        except:
            QMessageBox.warning(self, _('Error'), _('Invalid value') +': %s'%fee, _('OK'))
            return

        if self.wallet.fee != fee:
            self.wallet.fee = fee
            self.wallet.save()
        
        nz = unicode(nz_e.text())
        try:
            nz = int( nz )
            if nz>8: nz=8
        except:
            QMessageBox.warning(self, _('Error'), _('Invalid value')+':%s'%nz, _('OK'))
            return

        if self.wallet.num_zeros != nz:
            self.wallet.num_zeros = nz
            self.update_history_tab()
            self.update_receive_tab()
            self.wallet.save()

    @staticmethod 
    def network_dialog(wallet, parent=None):
        interface = wallet.interface
        if parent:
            if interface.is_connected:
                status = _("Connected to")+" %s:%d\n%d blocks"%(interface.host, interface.port, wallet.blocks)
            else:
                status = _("Not connected")
            server = wallet.server
        else:
            import random
            status = _("Please choose a server.")
            server = random.choice( DEFAULT_SERVERS )

        if not wallet.interface.servers:
            servers_list = []
            for x in DEFAULT_SERVERS:
                h,port,protocol = x.split(':')
                servers_list.append( (h,[(protocol,port)] ) )
        else:
            servers_list = wallet.interface.servers
            
        plist = {}
        for item in servers_list:
            host, pp = item
            z = {}
            for item2 in pp:
                protocol, port = item2
                z[protocol] = port
            plist[host] = z

        d = QDialog(parent)
        d.setModal(1)
        d.setWindowTitle(_('Server'))
        d.setMinimumSize(375, 20)

        vbox = QVBoxLayout()
        vbox.setSpacing(20)

        hbox = QHBoxLayout()
        l = QLabel()
        l.setPixmap(QPixmap(":icons/network.png"))
        hbox.addWidget(l)        
        hbox.addWidget(QLabel(status))

        vbox.addLayout(hbox)

        hbox = QHBoxLayout()
        host_line = QLineEdit()
        host_line.setText(server)
        hbox.addWidget(QLabel(_('Connect to') + ':'))
        hbox.addWidget(host_line)
        vbox.addLayout(hbox)

        hbox = QHBoxLayout()

        buttonGroup = QGroupBox(_("Protocol"))
        radio1 = QRadioButton("tcp", buttonGroup)
        radio2 = QRadioButton("http", buttonGroup)

        def current_line():
            return unicode(host_line.text()).split(':')
            
        def set_button(protocol):
            if protocol == 't':
                radio1.setChecked(1)
            elif protocol == 'h':
                radio2.setChecked(1)

        def set_protocol(protocol):
            host = current_line()[0]
            pp = plist[host]
            if protocol not in pp.keys():
                protocol = pp.keys()[0]
                set_button(protocol)
            port = pp[protocol]
            host_line.setText( host + ':' + port + ':' + protocol)

        radio1.clicked.connect(lambda x: set_protocol('t') )
        radio2.clicked.connect(lambda x: set_protocol('h') )

        set_button(current_line()[2])

        hbox.addWidget(QLabel(_('Protocol')+':'))
        hbox.addWidget(radio1)
        hbox.addWidget(radio2)

        vbox.addLayout(hbox)

        if wallet.interface.servers:
            label = _('Active Servers')
        else:
            label = _('Default Servers')
        
        servers_list_widget = QTreeWidget(parent)
        servers_list_widget.setHeaderLabels( [ label ] )
        servers_list_widget.setMaximumHeight(150)
        for host in plist.keys():
            servers_list_widget.addTopLevelItem(QTreeWidgetItem( [ host ] ))

        def do_set_line(x):
            host = unicode(x.text(0))
            pp = plist[host]
            if 't' in pp.keys():
                protocol = 't'
            else:
                protocol = pp.keys()[0]
            port = pp[protocol]
            host_line.setText( host + ':' + port + ':' + protocol)
            set_button(protocol)

        servers_list_widget.connect(servers_list_widget, SIGNAL('itemClicked(QTreeWidgetItem*, int)'), do_set_line)
        vbox.addWidget(servers_list_widget)

        vbox.addLayout(ok_cancel_buttons(d))
        d.setLayout(vbox) 

        if not d.exec_(): return
        server = unicode( host_line.text() )

        try:
            wallet.set_server(server)
        except:
            QMessageBox.information(None, _('Error'), 'error', _('OK'))
            if parent == None:
                sys.exit(1)
            else:
                return

        return True



class ElectrumGui():

    def __init__(self, wallet):
        self.wallet = wallet
        self.app = QApplication(sys.argv)

    def waiting_dialog(self):

        s = Timer()
        s.start()
        w = QDialog()
        w.resize(200, 70)
        w.setWindowTitle('Electrum')
        l = QLabel('')
        vbox = QVBoxLayout()
        vbox.addWidget(l)
        w.setLayout(vbox)
        w.show()
        def f():
            if self.wallet.up_to_date: 
                w.close()
            else:
                l.setText("Please wait...\nAddresses generated: %d\nKilobytes received: %.1f"\
                              %(len(self.wallet.all_addresses()), self.wallet.interface.bytes_received/1024.))

        w.connect(s, QtCore.SIGNAL('timersignal'), f)
        self.wallet.interface.poke()
        w.exec_()
        w.destroy()


    def restore_or_create(self):

        msg = _("Wallet file not found.")+"\n"+_("Do you want to create a new wallet, or to restore an existing one?")
        r = QMessageBox.question(None, _('Message'), msg, _('Create'), _('Restore'), _('Cancel'), 0, 2)
        if r==2: return False
        
        is_recovery = (r==1)
        wallet = self.wallet
        # ask for the server.
        if not ElectrumWindow.network_dialog( wallet, parent=None ): return False

        if not is_recovery:
            wallet.new_seed(None)
            wallet.init_mpk( wallet.seed )
            wallet.up_to_date_event.clear()
            wallet.up_to_date = False
            self.waiting_dialog()
            # run a dialog indicating the seed, ask the user to remember it
            ElectrumWindow.show_seed_dialog(wallet)
            #ask for password
            ElectrumWindow.change_password_dialog(wallet)
        else:
            # ask for seed and gap.
            if not ElectrumWindow.seed_dialog( wallet ): return False
            wallet.init_mpk( wallet.seed )
            wallet.up_to_date_event.clear()
            wallet.up_to_date = False
            self.waiting_dialog()
            if wallet.is_found():
                # history and addressbook
                wallet.update_tx_history()
                wallet.fill_addressbook()
                print "recovery successful"
                wallet.save()
            else:
                QMessageBox.information(None, _('Error'), _("No transactions found for this seed"), _('OK'))

        wallet.save()
        return True

    def main(self,url):
        s = Timer()
        s.start()
        w = ElectrumWindow(self.wallet)
        if url: w.set_url(url)
        w.app = self.app
        w.connect_slots(s)
        w.update_wallet()

        self.app.exec_()