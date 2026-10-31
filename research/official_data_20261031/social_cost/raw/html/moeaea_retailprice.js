$(document).ready(function () {
    var rootpath = document.querySelector('meta[name="web-rootpath"]')?.getAttribute('content') || '';
    var csvdata;

    //日期套件使用 bootstrap - datetimepicker
    $('.form_date').datetimepicker({
        startDate: '2000/01/01',
        language: 'zh-TW',
        weekStart: 0,
        todayBtn: 1,
        autoclose: 1,
        todayHighlight: 1,
        minView: 2,
    });

    //為日期套件的th加上scope屬性
    var $allThElements = document.getElementsByTagName("th");
    function customTh() {
        $.each($($allThElements), function (i) {
            $($allThElements[i]).attr('scope', "col");
        });
    }
    customTh();

    function updateSetting(data) {
        $('#startdayInput').val(data.start);
        $('#enddayInput').val(data.end);
    }

    function updateTable(data) {
        csvdata = data;
        $('#datarange').html(data.start + " ~ " + data.end);
        $("#datatable").empty();
        var Gasoline = data.gasoline;
        var cellData = '';
        cellData += '<div class="report_table fixed">';
        cellData += '    <table class="detail" cellspacing="0" rules="none">';
        cellData += '        <tbody>';
        cellData += '            <tr class="tr_title2">';
        cellData += '                <td>　</td>';
        cellData += '            </tr>';
        cellData += '            <tr class="tr_title">';
        cellData += '                <th>日期</th>';
        cellData += '            </tr>';
        $.each(Gasoline, function (index, value) {
            var tdclass = 'tr_odd';
            if (index % 2 == 1) {
                tdclass = 'tr_even';
            }
            cellData += '            <tr class="' + tdclass + '">';
            cellData += '                <td>' + value.Date + '</td>';
            cellData += '            </tr>';
        });
        cellData += '        </tbody>';
        cellData += '    </table>';
        cellData += '</div>';
        cellData += '<div class="table_wrapper">';
        cellData += '    <div class="report_table">';
        cellData += '        <table class="detail" cellspacing="0" rules="none">';
        cellData += '            <tbody>';
        cellData += '                <tr class="tr_title2">';
        cellData += '                    <td class="dividerL"></td>';
        cellData += '                    <td id="area1" colspan="5" class="dividerL">台灣中油</td>';
        cellData += '                    <td id="area2" colspan="5" class="dividerL">台塑石化</td>';
        cellData += '                </tr>';
        cellData += '                <tr class="tr_title">';
        cellData += '                    <th>施行日期</th>';
        cellData += '                    <th class="dividerL">施行時間</th>';
        cellData += '                    <th>92無鉛汽油</th>';
        cellData += '                    <th>95無鉛汽油</th>';
        cellData += '                    <th>98無鉛汽油</th>';
        cellData += '                    <th>超級柴油</th>';
        cellData += '                    <th class="dividerL">施行時間</th>';
        cellData += '                    <th>92無鉛汽油</th>';
        cellData += '                    <th>95無鉛汽油</th>';
        cellData += '                    <th>98無鉛汽油</th>';
        cellData += '                    <th>超級柴油</th>';
        cellData += '                </tr>';
        $.each(Gasoline, function (index, value) {
            cellData += '                <tr class="' + (index % 2 == 1 ? "tr_even" : "tr_odd") + '">';
            cellData += '                    <td>' + value.Date + '</td>';
            cellData += '                    <td class="dividerL">' + value.Astart + '時</td>';
            cellData += '                    <td>' + (value.A92 == null ? "N/A" : value.A92.toFixed(1)) + '</td>';
            cellData += '                    <td>' + (value.A95 == null ? "N/A" : value.A95.toFixed(1)) + '</td>';
            cellData += '                    <td>' + (value.A98 == null ? "N/A" : value.A98.toFixed(1)) + '</td>';
            cellData += '                    <td>' + (value.Achai == null ? "N/A" : value.Achai.toFixed(1)) + '</td>';
            cellData += '                    <td class="dividerL">' + value.Bstart + '時</td>';
            cellData += '                    <td>' + (value.B92 == null ? "N/A" : value.B92.toFixed(1)) + '</td>';
            cellData += '                    <td>' + (value.B95 == null ? "N/A" : value.B95.toFixed(1)) + '</td>';
            cellData += '                    <td>' + (value.B98 == null ? "N/A" : value.B98.toFixed(1)) + '</td>';
            cellData += '                    <td>' + (value.Bchai == null ? "N/A" : value.Bchai.toFixed(1)) + '</td>';
            cellData += '                </tr>';
        });
        cellData += '            </tbody>';
        cellData += '        </table>';
        cellData += '    </div>';
        cellData += '</div>';

        $("#datatable").append(cellData);
    }

    function initchart(init) {
        let formInit = new FormData();
        formInit.append('start', init);
        formInit.append('end', init);
        $.ajax({
            type: 'post',
            url: rootpath + '/Gasoline/RetailPrice/load',
            data: formInit,
            processData: false,
            contentType: false,
            success: function (data) {
                if (data.res == "01") {
                    updateSetting(data.data);
                    updateTable(data.data);
                } else {
                    $('#messagecontent').html("無汽柴油參考零售價資料");
                    $('#messageContentDialog').modal('show');
                    $('#message_list').focus();
                }
            },
            error: function (err) {
                $('#messagecontent').html("載入汽柴油參考零售價錯誤，如持續發生請聯繫工程人員");
                $('#messageContentDialog').modal('show');
                $('#message_list').focus();
            }
        });
    }
    initchart('init');

    function GetRangePrice(start, end) {
        if (start != "" && end != "") {
            if (start <= end) {
                let formInit = new FormData();
                formInit.append('start', start);
                formInit.append('end', end);
                $.ajax({
                    type: 'post',
                    url: rootpath + '/Gasoline/RetailPrice/load',
                    data: formInit,
                    processData: false,
                    contentType: false,
                    success: function (data) {
                        if (data.res == "01") {
                            updateTable(data.data);
                        } else {
                            $('#messagecontent').html(data.msg);
                            $('#messageContentDialog').modal('show');
                            $('#message_list').focus();
                        }
                    },
                    error: function (err) {
                        $('#messagecontent').html("載入區間汽柴油參考零售價格錯誤，如持續發生請聯繫工程人員");
                        $('#messageContentDialog').modal('show');
                        $('#message_list').focus();
                    }
                });
            }
            else {
                $('#messagecontent').html("請注意起始日期須小於結束日期，" + start + " > " + end);
                $('#messageContentDialog').modal('show');
                $('#message_list').focus();
            }
        }
        else {
            $('#messagecontent').html("請注意起始日期、結束日期皆須選擇");
            $('#messageContentDialog').modal('show');
            $('#message_list').focus();
        }
    }

    //日查詢
    $("#startdayInput").on("change.dp", function (e) {
        GetRangePrice($('#startdayInput').val(), $('#enddayInput').val());
    });

    $("#enddayInput").on("change.dp", function (e) {
        GetRangePrice($('#startdayInput').val(), $('#enddayInput').val());
    });

    $('.grid_tab a').click(function (event) {
        var index = $(this).index();

        $(this).addClass('current').siblings().removeClass('current');
        $(this).parent().next().children().eq(index).show().siblings().hide();
    });

    $('.short_guide').owlCarousel({
        loop: false,
        margin: 10,
        nav: true,
        dot: false,
        responsive: {
            0: {
                items: 1
            },
            572: {
                items: 3
            },
            992: {
                items: 5
            }
        }
    });

    $('#closemessage').click(function (event) {
        $('#messageContentDialog').modal('hide');
    });

    $('#downloadcsv').click(function (event) {
        var cellData = '供油商,台灣中油,台灣中油,台灣中油,台灣中油,台灣中油,台塑石化,台塑石化,台塑石化,台塑石化,台塑石化\n';
        cellData += '施行日期,施行時間,92無鉛汽油,95無鉛汽油,98無鉛汽油,超級柴油,施行時間,92無鉛汽油,95無鉛汽油,98無鉛汽油,超級柴油\n';
        $.each(csvdata.gasoline, function (index, value) {
            cellData += value.Date + ',';
            cellData += value.Astart + '時,';
            cellData += (value.A92 == null ? "N/A" : value.A92.toFixed(2)) + ',';
            cellData += (value.A95 == null ? "N/A" : value.A95.toFixed(2)) + ',';
            cellData += (value.A98 == null ? "N/A" : value.A98.toFixed(2)) + ',';
            cellData += (value.Achai == null ? "N/A" : value.Achai.toFixed(2)) + ',';
            cellData += value.Bstart + '時,';
            cellData += (value.B92 == null ? "N/A" : value.B92.toFixed(2)) + ',';
            cellData += (value.B95 == null ? "N/A" : value.B95.toFixed(2)) + ',';
            cellData += (value.B98 == null ? "N/A" : value.B98.toFixed(2)) + ',';
            cellData += (value.Bchai == null ? "N/A" : value.Bchai.toFixed(2)) + '\n';
        });

        let fileName = csvdata.start + " ~ " + csvdata.end + '汽柴油參考零售價.csv';

        // 建立一個 a，並點擊它
        let link = document.createElement('a');
        link.setAttribute('href', 'data:text/csv;charset=utf-8,%EF%BB%BF' + encodeURI(cellData));
        link.setAttribute('download', fileName);
        link.click();
    });
});