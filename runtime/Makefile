#
# GBA Editor — Makefile
# Tourne depuis build/ — chemins relatifs à build/
#
# Structure attendue dans build/ :
#   src/        → main.c généré + scripts C des acteurs
#   grit_out/   → tileset.h/.c + actor_*.h/.c (sorties grit)
#   obj/        → fichiers .o compilés
#   rom.elf     → ELF linkée
#   rom.gba     → ROM finale
#

ifeq ($(strip $(DEVKITPRO)),)
    $(error "DEVKITPRO non defini — configure via l editeur")
endif

DEVKITARM := $(DEVKITPRO)/devkitARM
PREFIX    := $(DEVKITARM)/bin/arm-none-eabi-
CC        := $(PREFIX)gcc
OBJCOPY   := $(PREFIX)objcopy
LD        := $(PREFIX)gcc

# Dossiers sources
SRC_DIRS  := src grit_out
# globals.c est dans src/ (généré par le transpileur Lua)
BUILD     := obj

# Collecter tous les .c dans src/ et grit_out/
CFILES    := $(foreach dir,$(SRC_DIRS),$(wildcard $(dir)/*.c))
# Fichier assembleur optionnel du soundbank maxmod
SFILES    := $(wildcard src/*.s)
OFILES    := $(addprefix $(BUILD)/,$(notdir $(CFILES:.c=.o))) \
             $(addprefix $(BUILD)/,$(notdir $(SFILES:.s=.o)))

# Flags de compilation
ARCH      := -mthumb-interwork -mthumb
CFLAGS    := $(ARCH) \
             -O2 -Wall \
             -mcpu=arm7tdmi -mtune=arm7tdmi \
             -fomit-frame-pointer \
             $(addprefix -I,$(SRC_DIRS)) \
             -I$(DEVKITPRO)/libgba/include \
             -isystem $(DEVKITPRO)/libtonc/include \
             -I$(DEVKITPRO)/maxmod/include

# Flags de link
# gba.specs est built-in dans arm-none-eabi-gcc
LDFLAGS   := $(ARCH) -specs=gba.specs
LIBS      := -L$(DEVKITPRO)/libgba/lib -L$(DEVKITPRO)/libtonc/lib \
             -L$(DEVKITPRO)/maxmod/lib -ltonc -lgba -lmm \
             -Wl,--allow-multiple-definition

TARGET    := rom

.PHONY: all clean

all: $(TARGET).gba

# ROM finale
$(TARGET).gba: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@
	@echo "[build] ROM: $@"

# ELF — ordre crucial: .o avant LIBS
$(TARGET).elf: $(OFILES) | $(BUILD)
	$(LD) $(LDFLAGS) -o $@ $^ $(LIBS)

# Compilation depuis src/
$(BUILD)/%.o: src/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c -o $@ $<

# Compilation depuis grit_out/
$(BUILD)/%.o: grit_out/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c -o $@ $<

# Assemblage soundbank (bin2s output)
$(BUILD)/%.o: src/%.s | $(BUILD)
	$(CC) $(ARCH) -x assembler-with-cpp -c -o $@ $<

# Créer obj/ si nécessaire
$(BUILD):
	mkdir -p $(BUILD)

clean:
	rm -rf $(BUILD) $(TARGET).elf $(TARGET).gba
