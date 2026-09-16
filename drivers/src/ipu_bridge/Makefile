KDIR ?= /lib/modules/$(shell uname -r)/build
PWD := $(CURDIR)

obj-m += ipu-bridge.o

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean
