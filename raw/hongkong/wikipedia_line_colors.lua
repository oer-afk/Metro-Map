local hk = "%1站 (香港)"
local tml = "%1站 (屯馬綫)"

local p = {
	["system title"] = "[[港鐵]]",
	["system color"] = "ad2a42",
	["system icon"] = "[[File:HK MTR logo.svg|x15px|link=港鐵|alt=港鐵]]",
	["line icon format"] = "link",
	["station format"] = {
		"%1站",
		
		["九龍塘"] = hk,
		["馬場"] = hk,
		["大學"] = hk,
		["太和"] = hk,
		["上水"] = hk,
		["羅湖"] = hk,
		["黃埔"] = hk,
		["藍田"] = hk,
		["九龍"] = "%1站 (港鐵)",
		["南昌"] = hk,
		["東涌"] = "%1站 (東涌綫)",
		["機場"] = hk,
		["坑口"] = hk,
		["康城"] = hk,
		["洪水橋"] = tml,
		["車公廟"] = hk,
		["石門"] = hk,
		["馬鞍山"] = hk,
		["迪士尼"] = hk,
		["沙田"] = hk,
		["新田"] = hk,
		["灣仔"] = hk,
		["皇崗口岸"] = hk,
		["東涌360"] = "[[東涌站 (昂坪360)|東涌]]",
	},
	["lines"] = {
		["_default"] = {
			["text color"] = "ffffff"
		},
		["東鐵綫"] = {
			["title"] = "[[東鐵綫]]",
			["icon"] = "[[File:東鐵綫 Hong Kong MTR East Rail Line.png|x18px|link=東鐵綫]]",
			["color"] = "53b7e8",
			["left terminus"] = "金鐘",
			["right terminus"] = {"羅湖","落馬洲"},
			["types"] = {
				["主線"] = {
					["right terminus"] = "羅湖"
				},
				["支線"] = {
					["right terminus"] = "落馬洲"
				}
			}
		},
		["屯馬綫"] = {
			["title"] = "[[屯馬綫]]",
			["icon"] = "[[File:屯馬綫 Hong Kong MTR Tuen Ma Line.png|x18px|link=屯馬綫]]",
			["color"] = "9a3b26",
			["left terminus"] = "屯門",
			["right terminus"] = "烏溪沙",
			["types"] = {
				["規劃中"] = {
					["title"] = "<div class='smA'>規劃中</div>",
					["left terminus"] = "屯門南"
				}
			}
		},
		["觀塘綫"] = {
			["title"] = "[[觀塘綫]]",
			["icon"] = "[[File:觀塘綫 Hong Kong MTR Kwun Tong Line.png|x18px|link=觀塘綫]]",
			["color"] = "1a9431",
			["text color"] = "ffffff",
			["left terminus"] = "黃埔",
			["right terminus"] = "調景嶺"
		},
		["荃灣綫"] = {
			["title"] = "[[荃灣綫]]",
			["icon"] = "[[File:荃灣綫 Hong Kong MTR Tsuen Wan Line.png|x18px|link=荃灣綫]]",
			["color"] = "ff0000",
			["left terminus"] = "中環",
			["right terminus"] = "荃灣"
		},
		["港島綫"] = {
			["title"] = "[[港島綫]]",
			["icon"] = "[[File:港島綫 Hong Kong MTR Island Line.png|x18px|link=港島綫]]",
			["color"] = "0860a8",
			["left terminus"] = "堅尼地城",
			["right terminus"] = "柴灣"
		},
		["將軍澳綫"] = {
			["title"] = "[[將軍澳綫]]",
			["icon"] = "[[File:將軍澳綫 Hong Kong MTR Tseung Kwan O Line.png|x18px|link=將軍澳綫]]",
			["color"] = "6b208b",
			["left terminus"] = "北角",
			["right terminus"] = {"寶琳", "康城"},
			["types"] = {
				["規劃中"] = {
					["title"] = "<div class='smA'>規劃中</div>",
				},
				["主線"] = {
					["right terminus"] = "寶琳"
				},
				["支線"] = {
					["right terminus"] = "康城"
				}
			}
		},
		["東涌綫"] = {
			["title"] = "[[東涌綫]]",
			["icon"] = "[[File:東涌綫 Hong Kong MTR Tung Chung Line.png|x18px|link=東涌綫]]",
			["color"] = "fe7f1d",
			["left terminus"] = "香港",
			["right terminus"] = "東涌",
			["types"] = {
				["規劃中"] = {
					["title"] = "<div class='smA'>規劃中</div>",
					["right terminus"] = "東涌西"
				}
			}
		},
		["機場快綫"] = {
			["title"] = "[[機場快綫 (港鐵)|機場快綫]]",
			["color"] = "1c7670",
			["icon"] = "[[File:AirportExpressMTR.svg|16px|link=機場快綫 (港鐵)]]",
			["left terminus"] = "香港",
			["right terminus"] = "博覽館"
		},
		["迪士尼綫"] = {
			["title"] = "[[迪士尼綫]]",
			["icon"] = "[[File:迪士尼綫 Hong Kong MTR Disneyland Resort Line.png|x18px|link=迪士尼綫]]",
			["color"] = "f550a6",
			["left terminus"] = "欣澳",
			["right terminus"] = "迪士尼"
		},
		["南港島綫"] = {
			["title"] = "[[南港島綫]]",
			["icon"] = "[[File:南港島綫 Hong Kong MTR South Island Line.png|x18px|link=南港島綫]]",
			["color"] = "b5bd00",
			["left terminus"] = "金鐘",
			["right terminus"] = "海怡半島"
		},
		["南港島綫西段"] = {
			["title"] = "[[南港島綫（西段）]]",
			["color"] = "9182c2",
			["left terminus"] = "香港大學",
			["right terminus"] = "黃竹坑"
		},
		["北港島綫"] = {
			["title"] = "[[北港島綫]]",
			["color"] = "fe7f1d",
			["left terminus"] = "香港",
			["right terminus"] = "北角"
		},
		["北環綫"] = {
			["title"] = "[[北環綫]]",
			["color"] = "a3238f",
			["left terminus"] = "錦上路",
			["right terminus"] = "古洞"
		},
		["新界東北綫"] = {
			["title"] = "[[新界東北綫]]",
			["color"] = "fe7f1d",
			["left terminus"] = "粉嶺",
			["right terminus"] = "香園圍"
		},
		["東九龍綫"] = {
			["title"] = "[[東九龍智慧綠色集體運輸系統]]",
			["color"] = "006633",
			["left terminus"] = "彩虹東",
			["right terminus"] = "油塘東"
		},
		["中鐵綫"] = {
			["title"] = "[[中鐵綫]]",
			["color"] = "000000",
			["left terminus"] = "錦上路",
			["right terminus"] = "九龍塘"
		},
		["廣九"] = {
			["title"] = "[[廣九直通車]]",
			["color"] = "824ca0",
			["left terminus"] = "廣州東",
			["right terminus"] = "紅磡"
		},
		["京九"] = {
			["title"] = "[[Z97/98次列車|京九直通車]]",
			["color"] = "008000",
			["left terminus"] = "北京西",
			["right terminus"] = "紅磡"
		},
		["滬九"] = {
			["title"] = "[[D99/100次列車|滬九直通車]]",
			["color"] = "ffa500",
			["left terminus"] = "上海",
			["right terminus"] = "紅磡"
		},
		["輕鐵"] = {
			["title"] = "[[香港輕鐵|輕鐵]]",
			["icon"] = "[[File:輕鐵 Hong Kong MTR Light Rail.png|x18px|link=香港輕鐵]]",
			["color"] = "D3A809"
		},
		["昂坪360"] = {
			["title"] = "[[昂坪360]]",
			["color"] = "94989A",
			["left terminus"] = "東涌360",
			["right terminus"] = "昂坪"
		},
		["高鐵"] = {
			["title"] = "[[廣深港高速鐵路香港段|高速鐵路]]",
			["color"] = "BBB0A3",
		},
		["廣深港高速鐵路香港段"] = {
			["title"] = "[[廣深港高速鐵路香港段]]",
			["color"] = "BBB0A3",
		},
		["修正早期系統"] = {
			["title"] = "[[修正早期系統]]",
			["color"] = "ff0000",
		},
		["西鐵綫"] = {
			["title"] = "[[西鐵綫]]",
			["color"] = "a3238f",
		},
		["馬鞍山綫"] = {
			["title"] = "[[馬鞍山綫]]",
			["color"] = "9a3b26",
		},
		["屯馬綫一期"] = {
			["title"] = "[[屯馬綫|屯馬綫一期]]",
			["color"] = "9a3b26",
		},
		["九廣東鐵"] = {
			["title"] = "[[東鐵綫|九廣東鐵]]",
			["color"] = "005DA0"
		},
		["九廣西鐵"] = {
			["title"] = "[[西鐵綫|九廣西鐵]]",
			["color"] = "A3238F"
		},
		["九廣馬鐵"] = {
			["title"] = "[[馬鞍山綫|馬鞍山鐵路]]",
			["color"] = "761E10"
		},
		["九廣輕鐵"] = {
			["title"] = "[[香港輕鐵|九廣輕鐵]]",
			["color"] = "FD722D"
		}
	},
	["aliases"] = {
		["eal"] = "東鐵綫",
		["東鐵"] = "東鐵綫",
		["ktl"] = "觀塘綫",
		["觀塘"] = "觀塘綫",
		["twl"] = "荃灣綫",
		["荃灣"] = "荃灣綫",
		["mis"] = "修正早期系統",
		["isl"] = "港島綫",
		["港島"] = "港島綫",
		["tcl"] = "東涌綫",
		["東涌"] = "東涌綫",
		["ael"] = "機場快綫",
		["機場"] = "機場快綫",
		["tkl"] = "將軍澳綫",
		["將軍澳"] = "將軍澳綫",
		["tml"] = "屯馬綫",
		["屯馬"] = "屯馬綫",
		["tmlp1"] = "屯馬綫一期",
		["drl"] = "迪士尼綫",
		["迪士尼"] = "迪士尼綫",
		['sil'] = '南港島綫',
		['南港島'] = '南港島綫',
		['南港島東'] = '南港島綫',
		['np360'] = '昂坪360',
		['360'] = '昂坪360',
		['mol'] = '馬鞍山綫',
		['馬鞍山'] = '馬鞍山綫',
		['wrl'] = '西鐵綫',
		['西鐵'] = '西鐵綫',
		["kcrer"] = "九廣東鐵",
		["kcrwr"] = "九廣西鐵",
		["kcrmos"] = "九廣馬鐵",
		["kcrlrt"] = "九廣輕鐵",
		["kcr-er"] = "九廣東鐵",
		["kcr-wr"] = "九廣西鐵",
		["kcr-mos"] = "九廣馬鐵",
		["kcr-lrt"] = "九廣輕鐵",
		["kcr-nol"] = "北環綫",
		["nol"] = "北環綫",
		["北環"] = "北環綫",
		["ekl"] = "東九龍綫",
		["東九龍"] = "東九龍綫",
		["nel"] = "新界東北綫",
		["新界東北"] = "新界東北綫",
		["silw"] = "南港島綫西段",
		["南港島西"] = "南港島綫西段",
		["nil"] = "北港島綫",
		["北港島"] = "北港島綫",
		["crl"] = "中鐵綫",
		["中鐵"] = "中鐵綫",
		["lrt"] = "輕鐵",
		["lr"] = "輕鐵",
		["xrl"] = "高鐵",
		["xrl-full"] = "廣深港高速鐵路香港段",
		["itt-gk"] = "廣九",
		["itt-sk"] = "滬九",
		["itt-bk"] = "京九",
	},
}

return p