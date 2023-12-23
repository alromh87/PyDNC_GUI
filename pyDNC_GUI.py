import os
import wx
import builtins
import subprocess
import threading
builtins.__dict__['_'] = wx.GetTranslation

class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(parent=None, title='pyDNC GUI')
        icon = wx.Icon()
        icon.LoadFile( 'logo.png', type=wx.BITMAP_TYPE_ANY, desiredWidth=-1, desiredHeight=-1)
        self.SetIcon(icon)

        panel = wx.Panel(self)

        self.received = 0

        sizerM = wx.BoxSizer(wx.VERTICAL)
        sizerH1 = wx.BoxSizer(wx.HORIZONTAL)
        sizerV = wx.BoxSizer(wx.VERTICAL)
        sizerH2 = wx.BoxSizer(wx.HORIZONTAL)

        self.btnSend = wx.Button(panel, label=_('Send'))
        self.btnRec = wx.Button(panel, label=_('Receive'))
        self.btnCanc = wx.Button(panel, label=_('Stop'))
        self.btnSet = wx.Button(panel, label=_('Settings'))
        self.ch_mach = wx.Choice(panel) # If shown as always open use ComboBox with style=wx.CB_READONLY
        self.console = wx.TextCtrl(panel, size=(300,300),style = wx.TE_MULTILINE | wx.TE_READONLY)
        self.status = self.CreateStatusBar()

        self.ch_mach.Bind(wx.EVT_CHOICE, self.on_machine_selection)
        self.btnSend.Bind(wx.EVT_BUTTON, self.on_send)
        self.btnRec.Bind(wx.EVT_BUTTON, self.on_receive)
        self.btnCanc.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.btnSet.Bind(wx.EVT_BUTTON, self.on_settings)

        sizerH2.Add(self.btnSend, 1, wx.ALL | wx.EXPAND, 5)
        sizerH2.Add(self.btnRec,  1, wx.ALL | wx.EXPAND, 5)
        sizerH2.Add(self.btnCanc,  1, wx.ALL | wx.EXPAND, 5)
        sizerV.Add(self.ch_mach, 3, wx.ALL | wx.EXPAND, 5)
        sizerV.Add(sizerH2, 0, wx.ALL | wx.EXPAND, 0)
        sizerH1.Add(self.btnSet, 1, wx.ALL | wx.EXPAND, 5)
        sizerH1.Add(sizerV, 1, wx.ALL | wx.EXPAND, 0)
        sizerM.Add(sizerH1, 0, wx.ALL | wx.EXPAND, 0)
        sizerM.Add(self.console, 3, wx.ALL | wx.EXPAND, 5)

        self.btnCanc.Hide()

        if not app.config.HasGroup('/Machines'):
            app.machines={}
            ConfigDialog(True).ShowModal()
        self.load_config()

        panel.SetSizer(sizerM)
        sizerM.SetSizeHints(self)

        self.Centre()
        self.Show()

    def load_config(self):
        app.machines = {}
        self.pydnc_conf = []
        self.pydnc = 'pydnc'
        if not app.config.HasGroup('/Machines'):
            return
        config = app.config
        oldPath = config.GetPath()
        #config.DeleteAll()
        #config.Flush()
        self.pydnc = config.Read('/pydnc')
        machine=config.Read('/last_machine')
        config.SetPath('/Machines')
        more, value, index = config.GetFirstGroup()
        while more:
            ''' In case using config is slow replace with local memory object
            config.SetPath('/Machines/%s'%value)
            settings = {}
            settings['port'] = config.Read('port')
            settings['data_bits'] = config.Read('data_bits')
            settings['stop_bits'] = config.Read('stop_bits')
            settings['baudrate'] = config.Read('baudrate')
            settings['parity'] = config.Read('parity')
            settings['flow_cont'] = config.Read('flow_cont')
            settings['d2'] = config.ReadBool('d2')
            settings['path'] = config.Read('path')
            config.SetPath('..')
            '''
            app.machines[value]=''
            if value == machine:
                self.parse_config(value)
            more, value, index = config.GetNextGroup(index)
            self.ch_mach.Set(list(app.machines.keys()))
            self.ch_mach.SetStringSelection(machine)

        config.SetPath(oldPath)

    def parse_config(self, name):
        self.pydnc_conf = []
        config = app.config
        oldPath = config.GetPath()
        config.SetPath('/Machines/%s'%name)
        self.pydnc_conf += ['-F', config.Read('port')]
        self.pydnc_conf.append('-c%s' % config.Read('data_bits'))
        self.pydnc_conf.append('-s%s' % config.Read('stop_bits'))
        self.pydnc_conf.append('-b%s' % config.Read('baudrate'))
        self.pydnc_conf += ['-p', config.Read('parity').lower()]
        '''
        self.pydnc_conf += ['-c', config.Read('data_bits')]
        self.pydnc_conf += ['-s', config.Read('stop_bits')]
        self.pydnc_conf += ['-b', config.Read('baudrate')]
        '''
        flow_cont = config.Read('flow_cont')
        if flow_cont == 'None':
            self.pydnc_conf.append('-x')
        elif flow_cont == 'Hardware':
            self.pydnc_conf.append('-w')
        if config.ReadBool('d2'): self.pydnc_conf += ['-d']
        #settings['path'] = config.Read('path')
        print(self.pydnc_conf)
        config.SetPath(oldPath)

    def enable_com_controls(self, enable):
        self.ch_mach.Enable(enable)
        self.btnSend.Show(enable)
        self.btnRec.Show(enable)
        self.btnCanc.Show(not enable)
        self.btnSet.Enable(enable)
        self.btnRec.GetParent().Layout()

    def run_pyDNC(self, path, receive=False):
        self.enable_com_controls(False)
        self.received = 0
        if len(self.console.GetValue()) > 0:
            self.console.AppendText('\n\n--------------------------------------------------------\n\n\n')
        args = ['python', self.pydnc] + self.pydnc_conf + ['-f', path]
        if receive:
            args += ['-r']
            self.codeDialog = CodeDialog(path)
        self.console.AppendText(' '.join(args) + '\n\n')
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.t = threading.Thread(target=self.process_pyDNC, args=(self.proc, receive))
        self.t.start()

    def process_pyDNC(self, p, receive):
        NOT_STARTED = 0
        OK = 1
        IGNORE_EMPTY = 2
        com_status = 0
        prev = b''
        self.code = bytearray()
        out=b''
        while p.poll() is None:
            out = p.stdout.readline()
            if len(out) > 0:
                wx.CallAfter(self.console.AppendText, out)	# Use this to edit ui component from non Ui thread
                if com_status == NOT_STARTED and out==b'\n': continue
                if receive:
                    if out.startswith('pyDNC: '.encode('utf-8')):
                        com_status = IGNORE_EMPTY
                        if out.startswith('pyDNC: EOT'.encode('utf-8')) and prev == b'\n':
                            out[:-1]
                            self.received -= 1
                        continue
                    if com_status == NOT_STARTED:
                        com_status = OK
                    if com_status == IGNORE_EMPTY and out==b'\n':
                        com_status = OK
                        continue
                    prev = out
                    self.received += len(out)
                    self.code += out
                    if len(out) > 1: wx.CallAfter(self.status.PushStatusText, _('%d bytes received'%self.received))
                    #TODO: calculate Hash
        else:
            out = p.stdout.read()
            wx.CallAfter(self.console.AppendText, out)
            r_code = p.poll()
            if r_code:
                if r_code == -9:
                    wx.CallAfter(self.status.PushStatusText, _('PyDNC aborted'))
                else:
                    wx.CallAfter(self.status.PushStatusText, _('PyDNC failed with code %d'%r_code))
            else:
                if receive:
                    for line in out.splitlines():
                        if not line.startswith('pyDNC: '.encode('utf-8')):
                            self.received += len(line)
                            self.code += line
                    if self.received > 0:
                        wx.CallAfter(self.status.PushStatusText, _('%d bytes received'%self.received))
                        wx.CallAfter(self.showFile)
                else:
                    wx.CallAfter(self.status.PushStatusText, _('Done'))
        wx.CallAfter(self.enable_com_controls,True)

    def showFile(self):
        self.codeDialog.load_mem(self.code)
        self.codeDialog.ShowModal()

    def on_machine_selection(self, event):
        machine = event.GetString()
        self.parse_config(machine)
        app.config.Write('/last_machine', machine)
        app.config.Flush()

    def on_send(self, event):
        with wx.FileDialog(self, _('Select file to send'), defaultDir=app.config.Read('/Machines/%s/path'%app.config.Read('last_machine')), style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            pathname = fileDialog.GetPath()
            self.run_pyDNC(pathname)
            self.status.PushStatusText(_('Starting send ... %s'%pathname))

    def on_receive(self, event):
        with wx.FileDialog(self, _('Select file location to save'), app.config.Read('/Machines/%s/path'%app.config.Read('last_machine')), style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            pathname = fileDialog.GetPath()
            self.run_pyDNC(pathname, True)
            self.status.PushStatusText(_('Starting receive ... %s'%pathname))

    def on_cancel(self, event):
        self.proc.kill()
        if self.received > 0:
            self.showFile()

    def on_settings(self, event):
        with ConfigDialog() as confDialog:
            if confDialog.ShowModal() == wx.ID_CANCEL:
                pass
            #    return
            #TODO: mark for changes needed
            self.load_config()


class CodeDialog(wx.Dialog):
    def __init__(self, file_path):
        self.file_name = file_path
        title = os.path.basename(file_path)
        super().__init__(parent=None, title=title, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        icon = wx.Icon()
        icon.LoadFile( 'logo.png', type=wx.BITMAP_TYPE_ANY, desiredWidth=-1, desiredHeight=-1)
        self.SetIcon(icon)

        panel = wx.Panel(self)
        sizerM = wx.BoxSizer(wx.VERTICAL)
        self.text = wx.TextCtrl(panel, size=(300,500), style = wx.TE_MULTILINE)
        sizerM.Add(self.text, 5, wx.ALL | wx.EXPAND, 5)

        panel.SetSizer(sizerM)
        sizerM.SetSizeHints(self)
        #self.Bind(wx.EVT_INIT_DIALOG, self.on_start) # Disable to load from memory
        self.Centre()


    def on_start(self, event):
        print("Starting...")
        self.load_file()
    def load_mem(self, data):
        self.text.write(data.decode('utf-8'));
        self.text.ShowPosition(0)

    def load_file(self):
        print('Loading %s'%self.file_name)
        with open(self.file_name, 'r') as f:
            self.text.write(f.read());
        self.text.ShowPosition(0)

class ConfigDialog(wx.Dialog):
    def __init__(self, first=False):
        super().__init__(parent=None, title='Machine Settings')
        icon = wx.Icon()
        icon.LoadFile( 'logo.png', type=wx.BITMAP_TYPE_ANY, desiredWidth=-1, desiredHeight=-1)
        self.SetIcon(icon)
        self.first = first

        panel = wx.Panel(self)

        sizerM = wx.GridBagSizer(4,5)
        sb = wx.StaticBox(panel, label=_("Serial comunication"))
        boxsizer = wx.FlexGridSizer(4, 3, (70,1))

        ports = ['/dev/ttyUSB0', '/dev/ttyUSB1']
        bauds = ['110', '300', '600', '1200', '2400', '4800', '9600', '14400', '19200', '38400', '56000', '57600', '76800', '86400', '115200', '128000', '256000']
        data_bits = ['5','6','7','8']
        stop_bits = ['1','2']
        parity = [_('None'),_('Even'),_('Odd'),_('Mark'),_('Space')]
        flow_cont = [_('Hardware'),_('Software'),_('None')]


        text_pydnc = wx.StaticText(panel, label=_('PyDNC Location'))
        self.tc_pydnc = wx.TextCtrl(panel)
        text_mach = wx.StaticText(panel, label=_('Machine'))
        self.ch_mach = wx.Choice(panel, choices=list(app.machines.keys()))
        text_port = wx.StaticText(sb, label=_('Port'))
        self.ch_port = wx.Choice(sb, choices=ports)
        text_d_bits = wx.StaticText(sb, label=_('Data bits'))
        self.ch_d_bits = wx.Choice(sb, choices=data_bits)
        text_s_bits = wx.StaticText(sb, label=_('Stop bits'))
        self.ch_s_bits = wx.Choice(sb, choices=stop_bits)
        text_baud = wx.StaticText(sb, label=_('Baudrate'))
        self.ch_baud = wx.Choice(sb, choices=bauds)
        text_parity = wx.StaticText(sb, label=_('Parity'))
        self.ch_parity = wx.Choice(sb,choices=parity)
        text_flow_cont = wx.StaticText(sb, label=_('Flow Control'))
        self.ch_flow_cont = wx.Choice(sb, choices=flow_cont)
        self.cb_enable_d2 = wx.CheckBox(panel, label=_('Send D2/D4 to start/stop communication'))
        text_path = wx.StaticText(panel, label=_('Default directory'))
        self.tc_path = wx.TextCtrl(panel)
        self.btn_add = wx.Button(panel, label=_('Add'))
        self.btn_del = wx.Button(panel, label=_('Remove'))
        self.btn_pydnc = wx.Button(panel, label=_('Browse..'))
        self.btn_dir = wx.Button(panel, label=_('Browse..'))
        self.btn_acc = wx.Button(panel, label=_('OK'), id=wx.ID_OK)
        self.btn_canc = wx.Button(panel, label=_('Cancel'), id=wx.ID_CANCEL)

        self.btn_pydnc.Bind(wx.EVT_BUTTON, self.on_search_pydnc)
        self.ch_mach.Bind(wx.EVT_CHOICE, self.on_machine_selection)
        self.btn_dir.Bind(wx.EVT_BUTTON, self.on_set_dir)
        self.btn_add.Bind(wx.EVT_BUTTON, self.on_add)
        self.btn_del.Bind(wx.EVT_BUTTON, self.on_delete)

        boxsizer.AddMany([
            (text_port, 1, wx.LEFT | wx.TOP | wx.EXPAND,9),
            (text_d_bits, 1, wx.LEFT | wx.TOP | wx.EXPAND,9),
            (text_s_bits, 1, wx.LEFT | wx.TOP | wx.EXPAND,9),
            (self.ch_port, 2, wx.LEFT | wx.BOTTOM | wx.EXPAND,5),
            (self.ch_d_bits, 2, wx.LEFT | wx.BOTTOM | wx.EXPAND,5),
            (self.ch_s_bits, 2, wx.LEFT | wx.BOTTOM | wx.EXPAND,5),
            (text_baud, 1, wx.LEFT | wx.TOP | wx.EXPAND,9),
            (text_parity, 1, wx.LEFT | wx.TOP | wx.EXPAND,9),
            (text_flow_cont, 1, wx.LEFT | wx.TOP | wx.EXPAND,9),
            (self.ch_baud, 1, wx.LEFT | wx.BOTTOM | wx.EXPAND,5),
            (self.ch_parity, 1, wx.LEFT | wx.BOTTOM | wx.EXPAND,5),
            (self.ch_flow_cont, 1, wx.LEFT | wx.BOTTOM | wx.EXPAND,5),
        ])

        sizerM.Add(text_pydnc, pos=(0,0), flag=wx.ALL | wx.EXPAND| wx.ALIGN_CENTER_VERTICAL, border=5)
        sizerM.Add(self.tc_pydnc, pos=(0,1), span=(1,3), flag=wx.ALL | wx.EXPAND, border=5)
        sizerM.Add(self.btn_pydnc, pos=(0,4), flag=wx.ALL | wx.EXPAND, border=5)
        sizerM.Add(text_mach, pos=(1,0), flag=wx.ALL | wx.EXPAND| wx.ALIGN_CENTER_VERTICAL, border=5)
        sizerM.Add(self.ch_mach, pos=(1,1), span=(1,2), flag=wx.ALL | wx.EXPAND, border=5)
        sizerM.Add(self.btn_add, pos=(1,3), flag=wx.ALL | wx.EXPAND, border=5)
        sizerM.Add(self.btn_del, pos=(1,4), flag=wx.ALL | wx.EXPAND, border=5)
        sizerM.Add(sb, pos=(2,0), span=(1,5), flag=wx.ALL | wx.EXPAND, border=5)
        sizerM.Add(self.cb_enable_d2, pos=(3,0), span=(1,3), flag=wx.ALL | wx.EXPAND, border=5)
        sizerM.Add(text_path, pos=(4,0), flag=wx.ALL | wx.EXPAND, border=5)
        sizerM.Add(self.tc_path, pos=(4,1), span=(1,3), flag=wx.ALL | wx.EXPAND, border=5)
        sizerM.Add(self.btn_dir, pos=(4,4), flag=wx.ALL | wx.EXPAND, border=5)
        sizerM.Add(self.btn_acc, pos=(5,3), flag=wx.ALL | wx.EXPAND, border=5)
        sizerM.Add(self.btn_canc, pos=(5,4), flag=wx.ALL | wx.EXPAND, border=5)

        sb.SetSizer(boxsizer)

        size = boxsizer.GetMinSize()
        border = sb.GetBordersForSizer()
        boxsizer.SetMinSize((size[0]+border[1],size[1]+2*border[0]))

        panel.SetSizer(sizerM)
        sizerM.SetSizeHints(self)

        machine = app.config.Read('/last_machine')
        self.load_config(machine)
        if self.first:
            wx.CallAfter(self.firstRun)

    def firstRun(self):
        wx.MessageDialog(self, _('Welcome to PyDNC_GUI please setup your machine to begin'), style= wx.ICON_INFORMATION).ShowModal()

    def load_config(self, machine):
        config = app.config
        print(machine)
        self.tc_pydnc.SetValue(config.Read('/pydnc'))
        if config.HasGroup('/Machines/%s'%machine):
            oldPath = config.GetPath()
            config.SetPath('/Machines/%s'%machine)
            self.ch_mach.SetStringSelection(machine)

            self.ch_port.SetStringSelection(config.Read('port'))
            self.ch_d_bits.SetStringSelection(config.Read('data_bits'))
            self.ch_s_bits.SetStringSelection(config.Read('stop_bits'))
            self.ch_baud.SetStringSelection(config.Read('baudrate'))
            self.ch_parity.SetStringSelection(config.Read('parity'))
            self.ch_flow_cont.SetStringSelection(config.Read('flow_cont'))
            self.cb_enable_d2.SetValue(config.ReadBool('d2'))
            self.tc_path.SetValue(config.Read('path'))
            config.SetPath(oldPath)
        else:
            print("loadDefaults")
            self.ch_port.SetSelection(0)
            self.ch_d_bits.SetSelection(3)
            self.ch_s_bits.SetSelection(0)
            self.ch_baud.SetSelection(6)
            self.ch_parity.SetSelection(0)
            self.ch_flow_cont.SetSelection(1)
            self.cb_enable_d2.SetValue(False)
            self.tc_path.SetValue('')

    def on_search_pydnc(self, event):
        with wx.FileDialog(self, _('Select pyDNC.py location'), style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            pathname = fileDialog.GetPath()
            self.tc_pydnc.SetValue(pathname)

    def on_machine_selection(self,event):
        self.load_config(event.GetString())

    def on_set_dir(self, event):
        with wx.DirDialog(self, _('Select default directory for machine'), style=wx.DD_DEFAULT_STYLE) as dirDialog:
            if dirDialog.ShowModal() == wx.ID_CANCEL:
                return
            pathname = dirDialog.GetPath()
            self.tc_path.SetValue(pathname)

    def on_add(self, event):
        with wx.TextEntryDialog(self, _('Machine name')) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            name = dialog.GetValue()
            indx = self.ch_mach.Append(name)
            self.ch_mach.SetSelection(indx)
            self.ch_mach.Enable(False)

    def on_delete(self, event):
        machine = self.ch_mach.GetStringSelection()
        if machine == "":
            wx.MessageDialog(self, _('Noting to delete'), style= wx.ICON_EXCLAMATION).ShowModal()
            return
        id = self.ch_mach.GetSelection()
        with wx.MessageDialog(self, _('Confirm deletion of %s')%machine, style=wx.YES_NO | wx.ICON_EXCLAMATION) as dialog:
            dialog.SetYesNoLabels(_('Confirm'), _('Cancel'))
            if dialog.ShowModal() == wx.ID_YES:
                app.config.DeleteGroup('/Machines/%s'%machine)
                app.config.Flush()
                self.ch_mach.Delete(id)
                if self.ch_mach.GetCount()>0: self.ch_mach.SetSelection(0)
                self.ch_mach.Enable(True)
                ''' TODO: use pub to update main GUI without reloading everything
if "2.8" in wx.version():
    import wx.lib.pubsub.setupkwargs
    from wx.lib.pubsub import pub
else:
    from wx.lib.pubsub import pub
                '''
                #del app.machines[machine]

    def TransferDataFromWindow(self):
        machine = self.ch_mach.GetStringSelection()
        if machine == "":
            wx.MessageDialog(self, _('Please add a machine to save'), style= wx.ICON_EXCLAMATION).ShowModal()
            return False
        config = app.config
        oldPath = config.GetPath()

        config.Write('/last_machine', machine)
        config.Write('/pydnc', self.tc_pydnc.GetValue() if len(self.tc_pydnc.GetValue())>0 else 'pydnc.py' )
        config.SetPath("/Machines/%s/"%machine)
        config.Write('port', self.ch_port.GetStringSelection())
        config.Write('data_bits',self.ch_d_bits.GetStringSelection())
        config.Write('stop_bits',self.ch_s_bits.GetStringSelection())
        config.Write('baudrate', self.ch_baud.GetStringSelection())
        config.Write('parity', self.ch_parity.GetStringSelection())
        config.Write('flow_cont', self.ch_flow_cont.GetStringSelection())
        config.WriteBool('d2', self.cb_enable_d2.IsChecked())
        config.Write('path', self.tc_path.GetValue())

        config.SetPath(oldPath)
        if not config.Flush():
            wx.MessageDialog(self, _('Error saving configuration'), style=wx.ICON_ERROR).ShowModal()
        return super().TransferDataFromWindow()

if __name__ == '__main__':
    app = wx.App()
    app.config = wx.Config('pyDNC_GUI')
    frame = MainFrame()
    app.MainLoop()
