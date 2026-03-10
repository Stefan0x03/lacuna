#ifndef TINY_H
#define TINY_H

#include <stddef.h>

/* Parse a user-supplied input string into a fixed internal buffer.
 * Returns 0 on success, -1 on error.
 */
int parse_input(const char *input);

/* Format a message using a user-supplied format string.
 * Returns a malloc'd string; caller must free().
 */
char *format_output(const char *fmt);

/* Resize an internal buffer to hold 'n' elements of 'elem_size' bytes.
 * Returns a pointer to the new buffer, or NULL on failure.
 */
void *resize_buffer(size_t n, size_t elem_size);

#endif /* TINY_H */
