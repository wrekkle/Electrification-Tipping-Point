function run_native_audit(output_root)
% Native audit entry point. Each script runs in a fresh output directory.
% Requires MATLAB plus logninv, nbinrnd and betarnd (Statistics toolbox).
% Example: run_native_audit(fullfile(pwd,'native_runs','run001'))
if nargin~=1
    error('Supply an explicit new output directory.');
end
if exist(output_root,'dir')
    error('Output directory already exists; use a new run name.');
end
required = {'logninv','nbinrnd','betarnd'};
for k=1:numel(required)
    if isempty(which(required{k}))
        error('Required function is unavailable: %s',required{k});
    end
end
base=fileparts(mfilename('fullpath'));
if ~is_absolute(output_root)
    output_root=fullfile(pwd,output_root);
end
mkdir(output_root);
previous=pwd;
restore=onCleanup(@() cd(previous)); %#ok<NASGU>
previous_visibility=get(groot,'defaultFigureVisible');
restore_visibility=onCleanup(@() set(groot,'defaultFigureVisible',previous_visibility)); %#ok<NASGU>
set(groot,'defaultFigureVisible','off');
fid=fopen(fullfile(output_root,'environment.txt'),'w');
fprintf(fid,'%s\n%s\n',version,evalc('ver'));
fclose(fid);
scripts={fullfile(base,'originals','final_tvr.m'), ...
    fullfile(base,'originals','final_tvr_v2_fluc_re.m'), ...
    fullfile(base,'review_fixes','final_tvr_review_fix.m'), ...
    fullfile(base,'review_fixes','final_tvr_v2_fluc_re_review_fix.m')};
failed={};
for k=1:numel(scripts)
    case_dir=fullfile(output_root,sprintf('case_%02d',k));
    mkdir(case_dir);
    copyfile(scripts{k},fullfile(case_dir,'case_script.m'));
    try
        execute_case(case_dir);
    catch err
        diary off;
        failed{end+1}=scripts{k}; %#ok<AGROW>
        fid=fopen(fullfile(case_dir,'error.txt'),'w');
        fprintf(fid,'%s',getReport(err,'extended','hyperlinks','off'));
        fclose(fid);
    end
end
cd(output_root);
fid=fopen('native_status.json','w');
fprintf(fid,'%s',jsonencode(struct('scripts',{scripts},'failed',{failed})));
fclose(fid);
if ~isempty(failed)
    error('%d native cases failed; inspect error.txt files.',numel(failed));
end
fprintf('All four scripts completed. This confirms execution, not paper reproduction.\n');
end

function execute_case(case_dir)
% The script's clear affects only this function workspace. The outer cleanup
% and script list survive. Local execution keeps XLSX output out of originals/.
cd(case_dir);
diary('console.log');
run('case_script.m');
save('workspace.mat','-v7');
writematrix(c8,'raw_c8.csv');
if exist('result_table','var')
    writetable(result_table,'result_table.csv');
end
figures=findall(groot,'Type','figure');
for k=1:numel(figures)
    exportgraphics(figures(k),sprintf('figure_%02d.png',k),'Resolution',160);
end
close all;
diary off;
end

function yes=is_absolute(path)
yes=~isempty(regexp(char(path),'^(?:[A-Za-z]:[\\/]|[/\\]{2}|/)','once'));
end
