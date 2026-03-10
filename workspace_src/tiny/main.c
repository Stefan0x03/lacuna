#include "tiny.h"

#include <stdio.h>
#include <stdlib.h>

/*
 * Minimal driver that exercises the three public API functions.
 * Used for manual testing and as a starting point for fuzzing.
 *
 * Usage:
 *   ./tiny <input_string>
 *
 * Examples:
 *   ./tiny "hello world"
 *   ./tiny "$(python3 -c 'print(\"A\"*100)')"        # triggers stack overflow
 *   ./tiny "%x %x %x %x"                              # triggers format string bug
 *   ./tiny "" 2305843009213693952 8                    # triggers integer overflow (decimal)
 *   ./tiny "" 0x2000000000000000 0x8                   # same via hex (strtoul handles 0x)
 */
int main(int argc, char *argv[])
{
    const char *input = (argc > 1) ? argv[1] : "hello world";

    /* Exercise parse_input */
    int tokens = parse_input(input);
    printf("parse_input: %d token(s)\n", tokens);

    /* Exercise format_output — user input used directly as format string */
    char *out = format_output(input);
    if (out) {
        printf("format_output: %s\n", out);
        free(out);
    }

    /* Exercise resize_buffer with caller-controlled sizes.
     * strtoul handles both decimal and 0x-prefixed hex values. */
    unsigned long n = 4;
    unsigned long esz = 16;
    if (argc > 2) n   = strtoul(argv[2], NULL, 0);
    if (argc > 3) esz = strtoul(argv[3], NULL, 0);

    void *buf = resize_buffer((size_t)n, (size_t)esz);
    if (buf) {
        printf("resize_buffer(%lu, %lu): allocated %lu bytes\n", n, esz, n * esz);
        free(buf);
    } else {
        printf("resize_buffer(%lu, %lu): returned NULL\n", n, esz);
    }

    return 0;
}
