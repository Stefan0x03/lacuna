#include "tiny.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* -----------------------------------------------------------------------
 * parse_input
 *
 * BUG: Stack buffer overflow via strcpy.
 *
 * 'buf' is a fixed 64-byte stack buffer. 'input' is copied into it with
 * strcpy(), which performs no length check. A caller who passes a string
 * longer than 63 characters will overflow the stack frame, corrupting the
 * saved return address or adjacent locals.
 *
 * Fix: use strncpy(buf, input, sizeof(buf) - 1) + explicit NUL terminator,
 * or snprintf(buf, sizeof(buf), "%s", input).
 * ----------------------------------------------------------------------- */
int parse_input(const char *input)
{
    char buf[64];

    if (input == NULL)
        return -1;

    /* VULNERABLE: no bounds check — overflows buf if strlen(input) >= 64 */
    strcpy(buf, input);

    /* Simulate processing: count tokens separated by spaces */
    int tokens = 0;
    char *p = buf;
    int in_token = 0;
    while (*p) {
        if (*p == ' ') {
            in_token = 0;
        } else if (!in_token) {
            in_token = 1;
            tokens++;
        }
        p++;
    }
    return tokens;
}

/* -----------------------------------------------------------------------
 * format_output
 *
 * BUG: Format string vulnerability.
 *
 * The caller-supplied 'fmt' is passed directly as the format argument to
 * printf() (and snprintf()). An attacker can supply format specifiers such
 * as %x, %s, or %n to read arbitrary stack memory or, with %n, write to
 * arbitrary memory addresses.
 *
 * Fix: use printf("%s", fmt) / snprintf(out, size, "%s", fmt).
 * ----------------------------------------------------------------------- */
char *format_output(const char *fmt)
{
    if (fmt == NULL)
        return NULL;

    /* First pass: compute required buffer size using the user fmt directly */
    /* VULNERABLE: fmt acts as the format string, not as data */
    int needed = snprintf(NULL, 0, fmt) + 1;
    if (needed <= 0)
        return NULL;

    char *out = malloc((size_t)needed);
    if (out == NULL)
        return NULL;

    /* Second pass: format into the allocated buffer */
    snprintf(out, (size_t)needed, fmt);  /* VULNERABLE again */
    return out;
}

/* -----------------------------------------------------------------------
 * resize_buffer
 *
 * BUG: Integer overflow in size calculation.
 *
 * The multiplication n * elem_size is performed in size_t arithmetic. On a
 * 64-bit system size_t is 64 bits, but n and elem_size are both caller-
 * controlled. When n == SIZE_MAX / elem_size + 1 (e.g. n=0x20000001,
 * elem_size=8) the product wraps around to a small value such as 8. malloc()
 * then allocates a tiny buffer, but the caller believes it received a much
 * larger one and writes past the end — heap buffer overflow.
 *
 * Fix: check for overflow before calling malloc:
 *   if (elem_size != 0 && n > SIZE_MAX / elem_size) return NULL;
 * ----------------------------------------------------------------------- */
void *resize_buffer(size_t n, size_t elem_size)
{
    if (n == 0 || elem_size == 0)
        return NULL;

    /* VULNERABLE: n * elem_size can wrap on large inputs */
    size_t total = n * elem_size;
    return malloc(total);
}
