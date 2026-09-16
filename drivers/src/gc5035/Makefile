KDIR ?= /lib/modules/$(shell uname -r)/build
PWD := $(CURDIR)

obj-m += gc5035.o

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean
