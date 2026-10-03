/* C, optimized: Apple's string.h and stdio.h then use their fortified forms
   (secure/_string.h, secure/_strings.h, secure/_stdio.h), as BlueWake's runtime does. */
#include <stdio.h>
#include <string.h>

__attribute__((visibility("default"))) int padmint_module_probe_c(char *out, unsigned long size, int value) {
    char buffer[32];
    memset(buffer, 0, sizeof buffer);
    snprintf(buffer, sizeof buffer, "padmint %d", value);
    memcpy(out, buffer, size < sizeof buffer ? size : sizeof buffer);
    return (int)strlen(buffer);
}
