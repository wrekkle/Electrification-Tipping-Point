function prei_write_text(path, text)
%PREI_WRITE_TEXT Write UTF-8 text. Callers own the output directory policy.

if ~ischar(path) || isempty(path)
    error('prei:io:path', 'A nonempty output path is required.');
end
if ~ischar(text)
    error('prei:io:text', 'Text must be a character array.');
end
fid = fopen(path, 'w', 'n', 'UTF-8');
if fid < 0
    error('prei:io:open', 'Cannot open output file: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', text);
end
