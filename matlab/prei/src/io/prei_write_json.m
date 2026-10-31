function prei_write_json(path, value)
%PREI_WRITE_JSON Write one JSON document using the interpreter encoder.

try
    text = jsonencode(value);
catch err
    error('prei:io:json', 'Cannot encode JSON: %s', err.message);
end
prei_write_text(path, [text sprintf('\n')]);
end
