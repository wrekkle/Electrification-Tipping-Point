function full_path = prei_abspath(path)
%PREI_ABSPATH Resolve a path against the current directory without requiring
%   platform-specific canonicalisation. Relative paths stay relative to pwd.

if ~ischar(path) || isempty(path)
    error('prei:path:input', 'A nonempty character path is required.');
end
if ~isempty(regexp(path, '^([/\\]|[A-Za-z]:)', 'once'))
    full_path = path;
else
    full_path = fullfile(pwd, path);
end
end
