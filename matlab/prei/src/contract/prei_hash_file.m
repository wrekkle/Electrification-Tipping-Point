function digest = prei_hash_file(path)
%PREI_HASH_FILE SHA-256 of a UTF-8 text file.

if ~ischar(path) || isempty(path)
    error('prei:hash:path', 'prei_hash_file expects a nonempty path.');
end
if exist(path, 'file') ~= 2
    error('prei:hash:missing', 'File not found: %s', path);
end
digest = prei_hash_text(fileread(path));
end
