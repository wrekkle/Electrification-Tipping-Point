function cleanup = prei_path_init()
%PREI_PATH_INIT Add this project's src directories for one call.
%   Returns an onCleanup object that restores the previous path. The entry
%   directory itself must already be on the path; no genpath is used.

root = fileparts(mfilename('fullpath'));
old_path = path();
cleanup = onCleanup(@() path(old_path));
src_dirs = {'contract', 'demand', 'allocation', 'cost', 'evaluation', 'summary', 'io'};
for i = 1:numel(src_dirs)
    addpath(fullfile(root, 'src', src_dirs{i}), '-begin');
end
end
