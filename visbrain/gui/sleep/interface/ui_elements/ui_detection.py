"""Main class for sleep tools managment."""
import numpy as np
from PyQt5 import QtWidgets, QtCore
import logging
from PyQt5.QtCore import Qt
from visbrain.utils import (remdetect, spindlesdetect, slowwavedetect,
                            kcdetect, peakdetect, mtdetect, artifacteegdetect,artifactecgdetect)
from visbrain.utils.sleep.event import _events_to_index

logger = logging.getLogger('visbrain')

# wy 纺锤波方法
USER_METHOD = {'Spindles': 'spindle', 'Slow waves': 'sw', 'K-complexes': 'kc',
               'REM': 'rem', 'Muscle twitches': 'mt', 'Peaks': 'peak', 'Spindles-a': 'spindle-a', 'Spindles-b': 'spindle-b',
               'Artifact-EEG': 'artifact-EEG', 'Artifact-ECG': 'artifact-ECG'}


class UiDetection(object):
    """Main class for sleep tools managment."""

    def __init__(self):
        """Init."""
        # =====================================================================
        # REM / SPINDLES / KC / SW / MT DETECTION
        # =====================================================================
        # Commonth elements :
        self._ToolDetectChan.addItems(self._channels)
        self._ToolDetectType.currentIndexChanged.connect(
            self._fcn_switch_detection)
        self._ToolDetectApply.clicked.connect(self._fcn_apply_detection)
        # Apply method (Selected / Visible / All) :
        self._ToolRdSelected.clicked.connect(self._fcn_apply_method)
        self._ToolRdViz.clicked.connect(self._fcn_apply_method)
        self._ToolRdAll.clicked.connect(self._fcn_apply_method)
        self._ToolDetectProgress.hide()
        self._fcn_switch_detection()

        # -------------------------------------------------
        # Location table :
        self._DetectChanSw.currentIndexChanged.connect(
            self._fcn_run_switch_location)
        self._DetectRm.clicked.connect(self._fcn_rm_location)
        self._DetectViz.clicked.connect(self._fcn_viz_location)
        self._DetecRmEvent.clicked.connect(self._fcn_rm_selected_event)
        # 添加按钮
        self._DetecAddEvent.clicked.connect(self._fcn_add_selected_event)
        self._DetectLocations.itemSelectionChanged.connect(
            self._fcn_goto_location)
        self._DetectLocations.cellChanged.connect(self._fcn_edit_detection)
        self._DetectionTab.setTabEnabled(1, False)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            # Perform actions to delete data
            self._fcn_rm_selected_event()
            # self.removeRow(row)
        # super().keyPressEvent(event)
    # =====================================================================
    # ENABLE / DISABLE GUI COMPONENTS (based on selected channels)
    # =====================================================================
    def _fcn_apply_method(self):
        """Be sure to apply hypnogram report only on selected channel."""
        viz = self._ToolRdSelected.isChecked()
        self._ToolDetectChan.setEnabled(viz)

    # =====================================================================
    # SWITCH DETECTION TYPE
    # =====================================================================
    def _fcn_switch_detection(self):
        """Switch between detection types (show / hide panels)."""
        idx = int(self._ToolDetectType.currentIndex())
        # wy纺锤波方法  添加方法的时候要修改这个
        # wy 伪迹界面

        if (idx >= 7):
            idx = 1;
        method = str(self._ToolDetectType.currentText())
        self._stacked_detections.setCurrentIndex(idx)
        enable = USER_METHOD[method] not in self._custom_detections.keys()
        self._stacked_detections.setEnabled(enable)

    # =====================================================================
    # RUN DETECTION
    # =====================================================================
    # -------------- Get channels to apply detection --------------
    def _fcn_get_chan_detection(self):
        """Get on which channel to apply the detection."""
        # Selected channel :
        if self._ToolRdSelected.isChecked():
            idx = [self._ToolDetectChan.currentIndex()]

        # Visible channels :
        elif self._ToolRdViz.isChecked():
            idx = [
                k for k in range(len(self)) if self._chanWidget[k].isVisible()]

        # All channels :
        elif self._ToolRdAll.isChecked():
            idx = range(len(self))

        return idx

    # -------------- Get the function to run --------------
    def _fcn_get_detection_function(self, method):
        """Get the method to use for the detection (default or custom).

        Parameters
        ----------
        method : string
            Method to use.
        """
        user_method = USER_METHOD[method]
        if user_method in self._custom_detections.keys():
            logger.warning("Custom method used for %s detection" % method)
            fcn = self._custom_detections[user_method]
        else:
            logger.info("Default method used for %s detection" % method)
            # Switch between detection types :
            if method == 'REM':
                th = self._ToolRemTh.value()
                rem_only = self._ToolRemOnly.isChecked()
                def fcn(data, sf, time, hypno):  # noqa
                    return remdetect(data, sf, hypno, rem_only, th)
            elif method == 'Spindles':
                thr = self._ToolSpinTh.value()
                fmin = self._ToolSpinFmin.value()
                fmax = self._ToolSpinFmax.value()
                tmin = self._ToolSpinTmin.value()
                tmax = self._ToolSpinTmax.value()
                nrem_only = self._ToolSpinRemOnly.isChecked()
                def fcn(data, sf, time, hypno):  # noqa
                    return spindlesdetect(data, sf, thr, hypno, nrem_only,
                                          fmin, fmax, tmin, tmax)
            # wy 纺锤波方法 Artifact-EEG
            elif method == 'Spindles-a':
                th = self._ToolRemTh.value()
                rem_only = self._ToolRemOnly.isChecked()

                def fcn(data, sf, time, hypno):  # noqa
                    return artifactecgdetect(data, sf, hypno, rem_only, th)
            # wy 纺锤波方法
            elif method == 'Spindles-b':
                th = self._ToolRemTh.value()
                rem_only = self._ToolRemOnly.isChecked()

                def fcn(data, sf, time, hypno):  # noqa
                    return artifactecgdetect(data, sf, hypno, rem_only, th)

            elif method == 'Artifact-EEG':
                fmin = self._ToolArtifactFmin.value()
                fmax = self._ToolArtifactFmax.value()
                thr  = self._ToolArtifactTh.value()
                # print(fmin,fmax,thr)

                def fcn(data, sf, time, hypno):  # noqa
                    return artifacteegdetect(self,data, sf, thr, fmin, fmax)

            elif method == 'Artifact-ECG':
                th = self._ToolRemTh.value()
                rem_only = self._ToolRemOnly.isChecked()

                def fcn(data, sf, time, hypno):  # noqa
                    return artifactecgdetect(data, sf, hypno, rem_only, th)
            elif method == 'Slow waves':
                thr = self._ToolWaveTh.value()
                def fcn(data, sf, time, hypno):  # noqa
                    return slowwavedetect(data, sf, thr)
            elif method == 'K-complexes':
                proba_thr = self._ToolKCProbTh.value()
                amp_thr = self._ToolKCAmpTh.value()
                tmin = self._ToolKCMinDur.value()
                tmax = self._ToolKCMaxDur.value()
                min_amp = self._ToolKCMinAmp.value()
                max_amp = self._ToolKCMaxAmp.value()
                nrem_only = self._ToolKCNremOnly.isChecked()
                def fcn(data, sf, time, hypno):  # noqa
                    return kcdetect(data, sf, proba_thr, amp_thr, hypno,
                                    nrem_only, tmin, tmax, min_amp, max_amp)
            elif method == 'Muscle twitches':
                th = self._ToolMTTh.value()
                rem_only = self._ToolMTOnly.isChecked()
                def fcn(data, sf, time, hypno):  # noqa
                    return mtdetect(data, sf, th, hypno, rem_only)
            elif method == 'Peaks':
                look = int(self._ToolPeakLook.value() * self._sf)
                _disp = self._ToolPeakMinMax.currentIndex()
                disp = ['max', 'min', 'minmax'][_disp]
                def fcn(data, sf, time, hypno):  # noqa
                    return peakdetect(sf, data, self._time, look, 1., disp,
                                      'auto')

        def fcn_check(data, sf, time, hypno):
            """Wrap fcn with type checking."""
            assert isinstance(data, np.ndarray)
            # wy 为Artifact-EEG添加一列表格
            # if method=='Artifact-EEG':
            #     idx,order = fcn(data, sf, time, hypno)
            # else:
            idx = fcn(data, sf, time, hypno)
            idx = np.asarray(idx)
            if not idx.size:
                return idx
            # Check indices shape and format to (n_events, 2) :
            # 伪迹
            if (idx.ndim == 2) and ((idx.shape[1] == 2) or (idx.shape[1] == 5)):  # (n_events, 2)
                return idx.astype(int)
            elif idx.ndim == 1:  # 1d vector
                if idx.dtype == bool:  # boolean array
                    assert len(idx) == len(data)
                    idx = np.arange(len(data))[idx]
                return _events_to_index(idx)
            else:
                raise ValueError("Return indices should either be an (n_events"
                                 ", 2) array or a boolean array of shape "
                                 "(n_time_points,) or an array with "
                                 "consecutive detected events.")

        return fcn_check

    # -------------- Run detection (only on selected channels) --------------
    def _fcn_apply_detection(self):
        """Apply detection (either REM/Spindles/Peaks/SlowWave/KC/MT)."""
        # Get channels to apply detection and the detection method :
        idx = self._fcn_get_chan_detection()
        method = str(self._ToolDetectType.currentText())
        artifact_all = [];
        fcn = self._fcn_get_detection_function(method)


        ############################################################
        # RUN DETECTION  wywywy 伪迹
        ############################################################
        if method == 'Artifact-ECG' and self._channels[7] == 'Euc':
            for i, k in enumerate(idx):
                if len(idx) > 1:
                    self._ToolDetectProgress.show()

                index = fcn(self._data[7, :], self._sf, self._time, self._hypno)
                nb = index.shape[0]
                dty = nb / (len(self._time) / self._sf / 60.)
                # dur = (index[:, 1] - index[:, 0]) * (1000. / self._sf)

                logger.info(("Perform %s detection on channel %s. %i events "
                             "detected.") % (method, self._channels[k], nb))
                if index.size:
                    # Enable detection tab :
                    self._DetectionTab.setTabEnabled(1, True)
                    self._detect.dict[(self._channels[k], method)]['index'] = index
                    # Be sure panel is displayed :
                    if not self._canvas_is_visible(k):
                        self._canvas_set_visible(k, True)
                        self._chan.visible[k] = True
                    self._chan.loc[k].visible = True
                    # Update progress bar :
                self._ToolDetectProgress.setValue(100. * (i + 1) / len(self))

        else:
            for i, k in enumerate(idx):
                # Display progress bar (only if needed):
                if len(idx) > 1:
                    self._ToolDetectProgress.show()

                # Run detection :
                # # wy 为Artifact-EEG添加一列表格
                # if method=='Artifact-EEG':
                #     index,order = fcn(self._data[k, :], self._sf, self._time, self._hypno)
                # else:
                index = fcn(self._data[k, :], self._sf, self._time, self._hypno)
                nb = index.shape[0]
                dty = nb / (len(self._time) / self._sf / 60.)
                # dur = (index[:, 1] - index[:, 0]) * (1000. / self._sf)

                logger.info(("Perform %s detection on channel %s. %i events "
                             "detected.") % (method, self._channels[k], nb))

                if index.size:
                    # Enable detection tab :
                    self._DetectionTab.setTabEnabled(1, True)
                    self._detect.dict[(self._channels[k], method)]['index'] = index
                    # Be sure panel is displayed :
                    if not self._canvas_is_visible(k):
                        self._canvas_set_visible(k, True)
                        self._chan.visible[k] = True
                    self._chan.loc[k].visible = True
                    # Update plot :
                    self._fcn_slider_move()
                # wy 如果是伪迹数据
                if index.shape[1] == 5:
                    # 保存每一次数据
                    artifact_all.extend(index.tolist());
                    # pass


                # Update progress bar :
                self._ToolDetectProgress.setValue(round(100. * (i + 1) / len(self)))
        # wy

        ############################################################
        # 满足有‘FP1’且是伪迹数据
        ############################################################
        if index.shape[1] == 5 and self._channels[0] =='Fp1':
            # 转numpy
            artifact_all = np.array(artifact_all);
            # 排序,先排start在排end
            arrSortedIndex = np.lexsort((artifact_all[:, 1], artifact_all[:, 0]))
            artifact_all = artifact_all[arrSortedIndex, :]
            # k全置为0  Fp1通道
            nb = artifact_all.shape[0]
            dty = nb / (len(self._time) / self._sf / 60.)
            # dur = (index[:, 1] - index[:, 0]) * (1000. / self._sf)

            logger.info(("伪迹结果并入%s通道，共检测出%i个伪迹 ") % (self._channels[0], nb))

            if artifact_all.size:
                # Enable detection tab :
                self._DetectionTab.setTabEnabled(1, True)
                self._detect.dict[(self._channels[0], method)]['index'] = artifact_all
                # Be sure panel is displayed :
                if not self._canvas_is_visible(0):
                    self._canvas_set_visible(0, True)
                    self._chan.visible[0] = True
                self._chan.loc[0].visible = True
                # Update plot :
                self._fcn_slider_move()
            # Update progress bar :
            self._ToolDetectProgress.setValue(100. * (i + 1) / len(self))

            # pass
        ############################################################
        # NUMBER // DENSITY
        ############################################################
        if index.size:
            # Report results on table :
            self._ToolDetectTable.setRowCount(1)
            self._ToolDetectTable.setItem(0, 0, QtWidgets.QTableWidgetItem(
                str(nb)))
            self._ToolDetectTable.setItem(0, 1, QtWidgets.QTableWidgetItem(
                str(round(dty, 2))))

        else:
            logger.error("No %s detected on channel %s. Adjust "
                         "parameters." % (method, self._channels[0]))

        ############################################################
        # LINE REPORT :
        ############################################################
        self._loc_line_report(select=True)

        # Activate the save detections menu and activate detection tab :
        self._check_detect_menu()

        # Finally, hide progress bar :
        self._ToolDetectProgress.hide()

    def _loc_line_report(self, *args, refresh=True, select=False):
        """Update line report."""
        self._detect.build_line(self._data)
        chans = self._detect.nonzero()
        # 如果refresh=True，更新下拉框数据
        if refresh:
            # Disconnect the table :
            self._DetectChanSw.disconnect()
            # Clear already existing events :
            self._DetectChanSw.clear()
            # Add list of detected event as (chan - type) :
            lst = []
            for k in chans.keys():
                for i in chans[k]:
                    lst.append(k + ' - ' + i)
            self._DetectChanSw.addItems(lst)
        self._fcn_run_switch_location()
        # Disable menu and detection tab if there is no detection :
        if self._DetectChanSw.count() == 0:
            self._DetectionTab.setTabEnabled(1, False)
        else:
            self._DetectionTab.setTabEnabled(1, True)
        self._check_detect_menu()
        # Reconnect table :
        self._DetectChanSw.currentIndexChanged.connect(
            self._fcn_run_switch_location)
        # Select the last detected event :
        if refresh and select:
            self._DetectChanSw.setCurrentIndex(self._DetectChanSw.count() - 1)

    # =====================================================================
    # FILL LOCATION TABLE
    # =====================================================================
    def _get_current_chan_type(self):
        """Return the currently selected channel and detection type."""
        chtp = tuple(str(self._DetectChanSw.currentText()).rsplit(' - '))
        return chtp if len(chtp) == 2 else ('', '')

    def __get_visible_loc(self):
        """Enable/Disable detection table accroding to the visibility."""
        # Get the currently selected channel and type :
        chan, tps = self._get_current_chan_type()
        if chan and tps:
            if tps == 'Peaks':
                viz = self._detect.peaks[(chan, tps)].visible
            else:
                viz = self._detect.line[(chan, tps)].visible
            self._DetectViz.setChecked(viz)
            self._DetectLocations.setEnabled(viz)

    def _fcn_rm_location(self):
        """Remove a detection."""
        # Get the currently selected channel and type :
        chan, types = self._get_current_chan_type()
        # Remove detection :
        if chan and types:
            self._detect.delete(chan, types)
            # Remove vertical indicators :
            pos = np.full((1, 3), -10., dtype=np.float32)
            self._chan.loc[self._channels.index(chan)].set_data(pos=pos)
            # Clean table :
            self._DetectLocations.setRowCount(0)
            # Update GUI :
            self._loc_line_report()
        else:
            self._DetectionTab.setTabEnabled(1, False)
            self._check_detect_menu()

    def _fcn_viz_location(self):
        """Display/hide detections."""
        # Get the currently selected channel and type :
        chan, types = self._get_current_chan_type()
        # Set visibility :
        if chan and types:
            viz = self._DetectViz.isChecked()
            self._detect.visible(viz, chan, types)
            self._chan.loc[self._channels.index(chan)].visible = viz
            self._DetectLocations.setEnabled(viz)

    def _fcn_run_switch_location(self):
        """Run switch location channel and type."""
        # Get the currently selected channel and type :
        chan, types = self._get_current_chan_type()
        # index_1 = self._detect[(chan, types)]['index']
        if chan and types:
            # Enable/disable the location table :
            self.__get_visible_loc()
            # Find index and durations :
            index = self._detect[(chan, types)]['index']
            # Get durations :
            dur = (index[:, 1] - index[:, 0]) * (1000. / self._sf)
            # Set hypnogram data :
            self._detect.build_hyp(chan, types)
            # Fill location table :
            # 下侧表格绘制
            self._fcn_fill_locations(chan, types, index, dur)

    def _fcn_fill_locations(self, channel, kind, index, duration):
        """Fill the location table."""
        # wy 给index排序
        # index.sort(axis=0,kind='quicksort',order=None)
        # Disconnect location table :
        self._DetectLocations.disconnect()
        ref = ['Wake', 'N1', 'N2', 'N3', 'REM', 'ART']
        # Clean table :
        self._DetectLocations.setRowCount(0)
        # Get starting index:
        sta_ind, end_ind = index[:, 0], index[:, 1]

        # Define the length of the table:
        self._DetectLocations.setRowCount(min(len(sta_ind), len(duration)))
        # Fill the table :
        # 开始循环读数据绘制表格
        for num, (k, j, i) in enumerate(zip(sta_ind, end_ind, duration)):
            # Starting :
            self._DetectLocations.setItem(num, 0, QtWidgets.QTableWidgetItem(
                str(self._time[k])))
            # Ending :
            self._DetectLocations.setItem(num, 1, QtWidgets.QTableWidgetItem(
                str(self._time[j])))
            # Duration :
            self._DetectLocations.setItem(num, 2, QtWidgets.QTableWidgetItem(
                str(i)))
            # Type :
            item = QtWidgets.QTableWidgetItem(ref[int(self._hypno[k])])
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            self._DetectLocations.setItem(num, 3, item)
        # wy 伪迹表格添加一列
        if (index.shape[1] == 5):
            # 顺序、功率、峰峰值
            artifact_order = index[:, 2]
            artifact_power = index[:, 3]
            artifact_peak2peak = index[:, 4]
            for num, (k, j, i) in enumerate(zip(artifact_order,artifact_power,artifact_peak2peak)):
                # 顺序
                self._DetectLocations.setItem(num, 4, QtWidgets.QTableWidgetItem(
                    str(k)))
                # 功率
                self._DetectLocations.setItem(num, 5, QtWidgets.QTableWidgetItem(
                    str(j)))
                # 峰峰值
                self._DetectLocations.setItem(num, 6, QtWidgets.QTableWidgetItem(
                    str(i)))



        # Go to the first detected event :
        # wy 换下拉框时自动跳转到第一个波形
        '''
        self._DetectLocations.selectRow(0)
        self._fcn_goto_location()
        '''

        # Reconnect :
        self._DetectLocations.itemSelectionChanged.connect(
            self._fcn_goto_location)
        self._DetectLocations.cellChanged.connect(self._fcn_edit_detection)


    # =====================================================================
    # GO TO THE LOCATION
    # =====================================================================
    # 指向右侧图表
    def _fcn_goto_location(self):
        """Go to the selected row REM / spindles / peak."""
        # Get the currently selected channel and type :
        chan, types = self._get_current_chan_type()
        # Get selected row and channel :
        row = self._DetectLocations.currentRow()
        ix = self._channels.index(chan)
        if row >= 0:
            # Get starting and ending point :
            sta = float(str(self._DetectLocations.item(row, 0).text()))
            end = float(str(self._DetectLocations.item(row, 1).text()))
            # Go to : 到右侧图对应位置
            self._SlGoto.setValue(sta)
            # Set vertical lines to the location : 俩竖线
            self._chan.set_location(self._sf, self._data[ix, :], ix, sta, end)

    # 编辑图表函数
    def _fcn_edit_detection(self):
        """Executed function when the item is edited."""
        # Get the currently selected channel and type :
        chan, types = self._get_current_chan_type()
        # Get selected row and col :
        row = self._DetectLocations.currentRow()
        col = self._DetectLocations.currentColumn()
        val = self._DetectLocations.item(row, col).text()
        if col in [0, 1]:  # Edit starting/ending point
            val = int(np.round(float(val) * self._sf))
            self._detect[(chan, types)]['index'][row, col] = val
        elif col == 2:  # Edit duration
            val = int(np.round(float(val) * self._sf / 1000.))
            start = self._detect[(chan, types)]['index'][row, 0]
            self._detect[(chan, types)]['index'][row, 1] = start + val
        elif col == 3:  # Avoid stage editing
            self._DetectLocations
            self._DetectLocations.setItem(row, 3,
                                          QtWidgets.QTableWidgetItem(val))
        # Update :
        self._loc_line_report(refresh=False)
        self._DetectLocations.selectRow(row)

    # 删除按钮函数
    def _fcn_rm_selected_event(self):
        """Remove the selected event in the table and update detections."""
        # Get selected row :
        row = self._DetectLocations.currentRow()  # return -1 when no more row
        if row + 1:
            # Remove row :_loc_line_report_remove
            self._DetectLocations.removeRow(row)
            # Get the currently selected channel and type :
            chan, types = self._get_current_chan_type()
            # 记录该位置
            tmp = self._detect[(chan, types)]['index']
            # Delete the selected event :
            index = self._detect[(chan, types)]['index']
            if not index.shape[0] - 1: #数据行数小于等于于1个
                self._detect.delete(chan, types)
                # Update :
                self._loc_line_report(refresh=True)
            else:
                # _detect[(chan, types)]['index']:  [[start end],[start end]...]
                self._detect[(chan, types)]['index'] = np.delete(index, row, 0)
                self._loc_line_report(refresh=False)
                # 光标指到该行
                self._DetectLocations.selectRow(row)
        # # wy 删除之后不跳转
        # self._SlGoto.setValue(tmp[row][0]/self._sf)
        # wy 删除之后跳转
        self._SlGoto.setValue(index[row+1][0] / self._sf)


    # 添加按钮函数
    # wy 改成排序按鈕了
    def _fcn_add_selected_event(self):
        # Get selected row :
        row = self._DetectLocations.currentRow()  # return -1 when no more row

        chan, types = self._get_current_chan_type()
        index = self._detect[(chan, types)]['index']
        # 伪迹
        if(index.shape[1] == 5):
            arrSortedIndex = np.lexsort((index[:, 1], index[:, 0], index[:, 2]))
        else:
            arrSortedIndex = np.lexsort((index[:, 1], index[:, 0]))
        index = index[arrSortedIndex, :]
        self._detect[(chan, types)]['index'] = index


        self._loc_line_report_add(refresh=False)

        # 光标指到第一行
        self._DetectLocations.selectRow(0)

    # ADD函数
    def _loc_line_report_add(self, *args, refresh=True, select=False):
        """Update line report."""
        self._detect.build_line(self._data)
        chans = self._detect.nonzero()
        # 如果refresh=True，更新下拉框数据
        if refresh:
            # Disconnect the table :
            self._DetectChanSw.disconnect()
            # Clear already existing events :
            self._DetectChanSw.clear()
            # Add list of detected event as (chan - type) :
            lst = []
            for k in chans.keys():
                for i in chans[k]:
                    lst.append(k + ' - ' + i)
            self._DetectChanSw.addItems(lst)
        self._fcn_run_switch_location_add()
        # Disable menu and detection tab if there is no detection :
        if self._DetectChanSw.count() == 0:
            self._DetectionTab.setTabEnabled(1, False)
        else:
            self._DetectionTab.setTabEnabled(1, True)
        self._check_detect_menu()
        # Reconnect table :
        self._DetectChanSw.currentIndexChanged.connect(
            self._fcn_run_switch_location)
        # Select the last detected event :
        if refresh and select:
            self._DetectChanSw.setCurrentIndex(self._DetectChanSw.count() - 1)


    def _fcn_run_switch_location_add(self):
        """Run switch location channel and type."""
        # Get the currently selected channel and type :
        chan, types = self._get_current_chan_type()
        if chan and types:
            # Enable/disable the location table :
            self.__get_visible_loc()
            # Find index and durations :
            index = self._detect[(chan, types)]['index']
            # Get durations :
            dur = (index[:, 1] - index[:, 0]) * (1000. / self._sf)
            # Set hypnogram data :
            self._detect.build_hyp(chan, types)
            # Fill location table :
            # 下侧表格绘制
            self._fcn_fill_locations_add(chan, types, index, dur)


    def _fcn_fill_locations_add(self, channel, kind, index, duration):
        """Fill the location table."""
        # Disconnect location table :
        self._DetectLocations.disconnect()
        ref = ['Wake', 'N1', 'N2', 'N3', 'REM', 'ART']
        # Clean table :
        self._DetectLocations.setRowCount(0)
        # Get starting index:
        sta_ind, end_ind = index[:, 0], index[:, 1]
        # Define the length of the table:
        self._DetectLocations.setRowCount(min(len(sta_ind), len(duration)))
        # Fill the table :
        # 开始循环读数据绘制表格
        for num, (k, j, i) in enumerate(zip(sta_ind, end_ind, duration)):
            # Starting :
            self._DetectLocations.setItem(num, 0, QtWidgets.QTableWidgetItem(
                str(self._time[k])))
            # Ending :
            self._DetectLocations.setItem(num, 1, QtWidgets.QTableWidgetItem(
                str(self._time[j])))
            # Duration :
            self._DetectLocations.setItem(num, 2, QtWidgets.QTableWidgetItem(
                str(i)))
            # Type :
            item = QtWidgets.QTableWidgetItem(ref[int(self._hypno[k])])
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            self._DetectLocations.setItem(num, 3, item)

            # wy 伪迹表格添加一列
            if (index.shape[1] == 5):
                # 顺序、功率、峰峰值
                artifact_order = index[:, 2]
                artifact_power = index[:, 3]
                artifact_peak2peak = index[:, 4]
                for num, (k, j, i) in enumerate(zip(artifact_order, artifact_power, artifact_peak2peak)):
                    # 顺序
                    self._DetectLocations.setItem(num, 4, QtWidgets.QTableWidgetItem(
                        str(k)))
                    # 功率
                    self._DetectLocations.setItem(num, 5, QtWidgets.QTableWidgetItem(
                        str(j)))
                    # 峰峰值
                    self._DetectLocations.setItem(num, 6, QtWidgets.QTableWidgetItem(
                        str(i)))


        # Go to the first detected event :
        self._DetectLocations.selectRow(0)
        # self._fcn_goto_location()
        # Reconnect :
        self._DetectLocations.itemSelectionChanged.connect(
            self._fcn_goto_location)
        self._DetectLocations.cellChanged.connect(self._fcn_edit_detection)

    # # wy伪迹并集
    # def _get_union_of_set:
    #     # 392
    #     pass

