KDIR ?= /lib/modules/$(shell uname -r)/build
PWD := $(CURDIR)

obj-m += intel_skl_int3472_discrete.o
intel_skl_int3472_discrete-y := discrete.o discrete_quirks.o clk_and_regulator.o led.o

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean
