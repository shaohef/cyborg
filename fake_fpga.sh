sed -i -e 's/^\(SYS_FPGA\) = "\(\/sys\/class\/fpga\)"$/\1 = "\/tmp\2"/g' cyborg/accelerator/drivers/fpga/intel/sysinfo.py
sed -i -e 's/^\(SYS_FPGA_PATH\) = "\(\/sys\/class\/fpga\)"$/\1 = "\/tmp\2"/g' cyborg/accelerator/drivers/fpga/utils.py
python cyborg/tests/unit/accelerator/drivers/fpga/intel/prepare_test_data.py
sudo echo 'echo fpgaconf $@' > /usr/bin/fpgaconf
sudo chmod a+x /usr/bin/fpgaconf
