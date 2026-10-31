function digest = prei_source_hash(root)
%PREI_SOURCE_HASH Hash relative paths and contents of every .m file under root.
%   The hash is computed before a run writes its output directory.

if ~ischar(root) || exist(root, 'dir') ~= 7
    error('prei:source:root', 'Source root is not a directory: %s', root);
end
files = prei_collect_m(root, '');
files = sort(files);
if isempty(files)
    error('prei:source:empty', 'No .m files found under %s.', root);
end
blob = '';
for i = 1:numel(files)
    path = fullfile(root, files{i});
    blob = [blob files{i} sprintf('\n') fileread(path) sprintf('\n')]; %#ok<AGROW>
end
digest = prei_hash_text(blob);
end

function files = prei_collect_m(root, prefix)
files = {};
entries = dir(root);
for i = 1:numel(entries)
    name = entries(i).name;
    if strcmp(name, '.') || strcmp(name, '..')
        continue;
    end
    path = fullfile(root, name);
    relative = fullfile(prefix, name);
    if entries(i).isdir
        sub = prei_collect_m(path, relative);
        files = [files; sub(:)]; %#ok<AGROW>
    elseif numel(name) > 2 && strcmp(name(end - 1:end), '.m')
        files{end + 1, 1} = relative; %#ok<AGROW>
    end
end
end
