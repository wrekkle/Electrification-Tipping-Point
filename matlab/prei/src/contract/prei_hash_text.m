function digest = prei_hash_text(text)
%PREI_HASH_TEXT Stable SHA-256 of a character array, Octave and MATLAB.
%   Uses the Octave core hash() when available and the JVM MessageDigest
%   otherwise. No random state is read or changed.

if ~ischar(text)
    error('prei:hash:input', 'prei_hash_text expects a character array.');
end

if exist('OCTAVE_VERSION', 'builtin') == 5
    digest = hash('sha256', text);
else
    try
        md = java.security.MessageDigest.getInstance('SHA-256');
        md.update(uint8(text));
        bytes = typecast(md.digest(), 'uint8');
        digest = lower(reshape(dec2hex(bytes, 2)', 1, []));
    catch err
        error('prei:hash:unavailable', ...
            'No SHA-256 implementation available: %s', err.message);
    end
end

digest = char(digest);
end
