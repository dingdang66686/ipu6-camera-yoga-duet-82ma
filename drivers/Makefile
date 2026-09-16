# SPDX-License-Identifier: GPL-2.0
# Top-level DKMS Makefile for yoga-duet-ipu6-cameras
#
# DKMS feeds a single MAKE array entry using this Makefile so that the five
# out-of-tree camera modules compile SERIALLY.  Building independent MAKE[]
# entries in parallel trips a race in the shared /lib/modules/.../build kernel
# tree (parallel MODPOST / BTF), which made gc5035 / ipu-bridge fail
# intermittently under `dkms build`.
#
# NOTE: the four sensor/bridge .c sources are produced by scripts/prepare.sh
# (DKMS PRE_BUILD) from an upstream baseline + our patches.  The PSYS sources
# under src/psys/ are vendored verbatim (PSYS is fully out-of-tree and its
# headers are not available from the kernel tree), so prepare.sh does NOT touch
# them.  This Makefile only compiles whatever lives in src/ at build time.

KDIR ?= /lib/modules/$(shell uname -r)/build
LLVM   ?= 1

SUBDIRS := ov5678 gc5035 ipu_bridge int3472 psys

# Modules produced in each subdir -> expected .ko name at build root.
KO_ov5678    := ov5678.ko
KO_gc5035    := gc5035.ko
KO_ipu_bridge := ipu-bridge.ko
KO_int3472   := intel_skl_int3472_discrete.ko
KO_psys      := intel-ipu6-psys.ko

# DKMS expects every BUILT_MODULE_NAME to live under BUILT_MODULE_LOCATION
# relative to this (build root) directory, so we copy all five .ko here.
all:
	@set -e; for d in $(SUBDIRS); do \
		echo "  >> building $$d"; \
		$(MAKE) -C src/$$d KDIR=$(KDIR) LLVM=$(LLVM); \
	done
	@set -e; \
	  cp -f src/ov5678/$(KO_ov5678)         ./ ; \
	  cp -f src/gc5035/$(KO_gc5035)         ./ ; \
	  cp -f src/ipu_bridge/$(KO_ipu_bridge) ./ ; \
	  cp -f src/int3472/$(KO_int3472)       ./ ; \
	  cp -f src/psys/$(KO_psys)             ./ ; \
	  echo "  >> staged: ov5678.ko gc5035.ko ipu-bridge.ko intel_skl_int3472_discrete.ko intel-ipu6-psys.ko"

clean:
	@for d in $(SUBDIRS); do \
		$(MAKE) -C src/$$d KDIR=$(KDIR) LLVM=$(LLVM) clean; \
	done
	@rm -f ./*.ko ./.*.ko.cmd ./Module.symvers ./.Module.symvers.cmd ./modules.order 2>/dev/null || true
