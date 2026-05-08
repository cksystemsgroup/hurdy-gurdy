    .text
    .globl  _start
    .type   _start, @function
_start:
    lui     x6, 0x40            # x6 = 0x40000
    lui     x5, 0xAABBD         # x5 = 0xAABBD000
    addi    x5, x5, -0x223      # x5 = 0xAABBD000 - 0x223 = 0xAABBCDDD
                                # (low 32 = 0xAABBCDDD; bit 31 = 1)
    sw      x5, 0(x6)           # mem[0x40000..0x40003] = (LE) DD CD BB AA
    lh      x10, 0(x6)          # x10 = sign_extend(mem[0x40000:2], 64)
                                #     = sign_extend(0xCDDD)
                                #     = 0xFFFFFFFFFFFFCDDD  (bit 15 set)
    ebreak
    .size   _start, .-_start
