function env = prei_environment()
%PREI_ENVIRONMENT Describe the interpreter actually executing this call.
%   This function only reads version strings and environment variables. It
%   never calls rng/rand and never writes files.

env = struct();
env.platform = computer();
env.is_octave = exist('OCTAVE_VERSION', 'builtin') == 5;
env.release = version();
if env.is_octave
    env.octave_version = OCTAVE_VERSION;
    env.matlab_version = '';
else
    env.octave_version = '';
    env.matlab_version = version();
end

host = getenv('COMPUTERNAME');
if isempty(host)
    host = getenv('HOSTNAME');
end
env.hostname = host;
env.timestamp_local = datestr(now, 'yyyy-mm-dd HH:MM:SS');
env.random_state_touched = false;

% The authoring session for this static core executed Octave only. A MATLAB
% call must not silently turn this flag into a claim of MATLAB verification.
env.octave_tested = env.is_octave;
env.matlab_tested = false;
env.verification_scope = 'static_core_and_entrypoint_smoke_tests';
end
