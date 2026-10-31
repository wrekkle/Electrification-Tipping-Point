function prei_self_test()
%PREI_SELF_TEST Run the static test script with only the entry directory added.
%   The caller adds matlab/prei to the path; this wrapper does not use genpath.

path_cleanup = prei_path_init(); %#ok<NASGU>
run_prei_tests();
end
