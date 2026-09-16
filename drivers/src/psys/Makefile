# SPDX-License-Identifier: GPL-2.0
#
# Makefile for the vendored Intel IPU6 PSYS driver (intel-ipu6-psys.ko).
#
# PSYS is NOT part of mainline Linux and is NOT provided by the in-tree
# /lib/modules/$(uname -r)/build tree (that tree ships neither the ipu6*.h /
# ipu*.h headers nor a psys/ directory).  All headers it needs are therefore
# vendored flat alongside the sources in this directory, and we add the
# current directory to the include path.
#
# Sources are a verbatim copy of the upstream Intel ipu6-drivers repository
# (https://github.com/intel/ipu6-drivers), path
# drivers/media/pci/intel/ipu6/psys/, GPL-2.0.

KDIR ?= /lib/modules/$(shell uname -r)/build
PWD  := $(CURDIR)

# PSYS relies on this export to disable the in-tree `src := $(srctree)/$(src)`
# rewrite (see upstream Makefile) and to pick up the vendored headers.
export EXTERNAL_BUILD = 1
export CONFIG_VIDEO_INTEL_IPU6 = m

obj-m += intel-ipu6-psys.o
intel-ipu6-psys-y := \
	ipu-psys.o \
	ipu-fw-psys.o \
	ipu-fw-resources.o \
	ipu-resources.o \
	ipu6-psys.o \
	ipu6-ppg.o \
	ipu6-l-scheduler.o \
	ipu6-fw-resources.o \
	ipu6se-fw-resources.o \
	ipu6ep-fw-resources.o

# Vendored headers live in this same directory (flat).
ccflags-y += -I$(src)/

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean
