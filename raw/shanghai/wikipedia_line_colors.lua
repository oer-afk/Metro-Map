local x = "%1站 (上海市)"
local d = "%1站 (地铁)"

local p = {
	["system title"] = "[[上海地铁]]",
	["line icon format"] = "route",
	["station format"] = {
		"%1站",
		-- 消歧义
		-- 1号线
		["莘庄"] = d,
		["衡山路"] = x,
		["人民广场"] = x,
		["中山北路"] = x,
		
		-- 2号线
		["国家会展中心"] = x,
		["虹桥2号航站楼"] = d,
		["中山公园"] = x,
		["世纪大道"] = x,
		
		-- 3号线
		["延安西路"] = x,
		["长江南路"] = x,
		["友谊路"] = x,
		
		-- 4号线
		["大连路"] = x,
		["鲁班路"] = x,

		-- 5号线
		["西渡"] = x,
		
		-- 6号线
		
		-- 7号线
		["长寿路"] = x,
	
		-- 8号线
		["中兴路"] = x,
		["大世界"] = x,

		-- 9号线
		["七宝"] = d,
		["小南门"] = x,
		["金桥"] = x,

		-- 10号线
		["交通大学"] = x,
		["五角场"] = x,
		["高桥西"] = x,
		["高桥"] = x,

		-- 11号线
		["花桥"] = "[[花桥站 (昆山市地铁车站)|花桥]]",
		["安亭"] = d,
		["南翔"] = d,
		["龙华"] = x,
		["云锦路"] = x,
		["迪士尼"] = x,

		-- 12号线
        ["金海路"] = x,
        
		-- 13号线
		["前湾公园"] = x,

		-- 14号线
		["封浜"] = d,

		-- 15号线

		-- 16号线
		["新场"] = x,
		["书院"] = x,

		-- 17号线

		-- 18号线
		["下沙"] = x,
		["繁荣路"] = x,
		["周浦"] = x,
		["迎春路"] = x,
		
		-- 19号线
		["华丰路"] = x,
		
		-- 20号线
		
		-- 21号线
		["六团"] = "[[六团社区应急物资配送中心|六团]]",
		
		-- 22号线
		["东滩"] = x,
		
		-- 23号线
		
		-- 浦江线
		
		-- 磁浮线
		
		-- 模板格式需要
		['外圈'] = "外圈",
		['内圈'] = "内圈",
	},
	["lines"] = {
		["_default"] = {
			["title"] = "[[上海轨道交通%1号线|%1号线]]",
			["color"] = "000000",
			['text color'] = "FFFFFF",
			['icon'] = "[[File:Shmetro Line %1 Logo.svg|x20px|link=上海轨道交通%1号线|alt=%1]]",
		},
		["1"] = {
			["color"] = "E3002B",
			["left terminus"] = "莘庄",
			["right terminus"] = "富锦路"
		},
		["2"] = {
			["color"] = "82BF25",
			['text color'] = "000000",
			["left terminus"] = "蟠祥路·国家会计学院",
			["right terminus"] = "浦东1号2号航站楼",
        },
		["3"] = {
			["color"] = "FCD600",
			['text color'] = "000000",
			["left terminus"] = "上海南站",
			["right terminus"] = "江杨北路"
		},
		["4"] = {
			["color"] = "461D84",
			["circular"] = true,
			["left terminus"] = "外环",
			["right terminus"] = "内环"
		},
		["5"] = {
			["color"] = "944D9A",
			["left terminus"] = "莘庄",
			["right terminus"] = { "奉贤新城","闵行开发区" },
			["types"] = {
				["主线"] = {
					["title"] = "",
					["right terminus"] = "奉贤新城",
                },
                ["规划中"] = {
                    ["title"] = "<div class='smA'>规划中</div>",
                    ["right terminus"] = "平庄公路"
                },
				["支线"] = {
					["title"] = "",
					["right terminus"] = "闵行开发区"
		        },
			},
		},
		["6"] = {
			["color"] = "D40068",
			["left terminus"] = "港城路",
			["right terminus"] = "东方体育中心"
		},
		["7"] = {
			["color"] = "ED6F00",
			['text color'] = "000000",
			["left terminus"] = "美兰湖",
			["right terminus"] = "花木路"
		},
		["8"] = {
			["color"] = "0094D8",
			["left terminus"] = "市光路",
			["right terminus"] = "沈杜公路"
		},
		["9"] = {
			["color"] = "87CAED",
			['text color'] = "000000",
			["left terminus"] = "上海松江站",
			["right terminus"] = "曹路",
            ["types"] = {
				["规划中"] = {
					["title"] = "<div class='smA'>规划中</div>",
					["right terminus"] = "曹路火车站"
				},
			},
		},
		["10"] = {
			["color"] = "C6AFD4",
			['text color'] = "000000",
			["left terminus"] = { "虹桥火车站","航中路" },
			["right terminus"] = "基隆路",
			["types"] = {
				["主线"] = {
					["title"] = "",
					["left terminus"] = "虹桥火车站"
				},
				["支线"] = {
					["title"] = "",
					["left terminus"] = "航中路"
				},
			},
		},
		["11"] = {
			["color"] = "871C2B",
			["left terminus"] = { "嘉定北","花桥" },
			["right terminus"] = "迪士尼",
			["types"] = {
				["主线"] = {
					["title"] = "",
					["left terminus"] = "嘉定北"
				},
				["支线"] = {
					["title"] = "",
					["left terminus"] = "花桥"
				},
			},
		},
		["12"] = {
			["color"] = "007B61",
			["left terminus"] = "七莘路",
			["right terminus"] = "金海路",
			["types"] = {
				["建设中"] = {
					["title"] = "<div class='smA'>建设中</div>",
					["left terminus"] = "洞泾"
				},
			},
		},
		["13"] = {
			["color"] = "E999C0",
			['text color'] = "000000",
			["left terminus"] = "金运路",
			["right terminus"] = "张江路",
			["types"] = {
				["建设中"] = {
					["title"] = "<div class='smA'>建设中</div>",
					["left terminus"] = "国家会展中心",
					["right terminus"] = "丹桂路"
				},
            },
		},
		["14"] = {
			["color"] = "626020",
			["left terminus"] = "封浜",
			["right terminus"] = "桂桥路"
		},
		["15"] = {
			["color"] = "BCA886",
			['text color'] = "000000",
			["left terminus"] = "紫竹高新区",
			["right terminus"] = "顾村公园",
			["types"] = {
				["建设中"] = {
					["title"] = "<div class='smA'>建设中</div>",
					["left terminus"] = "望园路"
				},
			},
		},
		["16"] = {
			["color"] = "98D1C0",
			['text color'] = "000000",
			["left terminus"] = "龙阳路",
			["right terminus"] = "滴水湖"
		},
		["17"] = {
			["color"] = "BC796F",
			["left terminus"] = "西岑",
			["right terminus"] = "虹桥火车站"
		},
		["18"] = {
			["color"] = "C4984F",
			['text color'] = "000000",
			["left terminus"] = "航头",
			["right terminus"] = "康文路"
		},
		["19"] = {
			["color"] = "F5AB78",
			['text color'] = "000000",
		    ["left terminus"] = "虹建路",
			["right terminus"] = "上海宝山站"
		},
		["20"] = {
			["color"] = "009F65",
            ["left terminus"] = "交通路",
			["right terminus"] = "北新园路"
		},
		["21"] = {
			["color"] = "F7AF00",
			['text color'] = "000000",
            ["left terminus"] = "浦东3号航站楼",
			["right terminus"] = "东靖路"
		},
		["22"] = {
			["color"] = "5F376F",
            ["left terminus"] = "金吉路",
			["right terminus"] = "裕安"
		},
		["23"] = {
			["color"] = "B0D478",
			['text color'] = "000000",
            ["left terminus"] = "闵行开发区",
			["right terminus"] = "上海体育场"
		},
		["26"] = {
			["color"] = "5F67A9"
		},
		["浦江"] = {
			["title"] = "[[上海轨道交通浦江线|浦江线]]",
			["icon"] = "[[File:Shmetro Pujiang Line Logo.svg|x20px|link=上海轨道交通浦江线|alt=浦江线]]",
			["color"] = "B5B5B6",
			['text color'] = "FFFFFF",
			["left terminus"] = "沈杜公路",
			["right terminus"] = "汇臻路"
		},
		["磁浮"] = {
			["title"] = "[[上海磁浮示范运营线|磁浮线]]",
			["icon"] = "[[File:Shmetro Maglev Line Logo.svg|x20px|link=上海磁浮示范运营线|alt=磁浮线]]",
			["color"] = "008B9A",
  			["left terminus"] = "龙阳路",
  			["right terminus"] = "浦东1号2号航站楼"
		},
		["上海磁浮示范运营线"] = { -- same as 磁浮 but in full name instead
			["title"] = "[[上海磁浮示范运营线]]",
			["icon"] = "[[File:Shmetro Maglev Line Logo.svg|x20px|link=上海磁浮示范运营线|alt=磁浮线]]",
			["color"] = "008B9A",
  			["left terminus"] = "龙阳路",
  			["right terminus"] = "浦东1号2号航站楼"
		},
	},
	["aliases"] = {
		["c"] = "22",
		["cml"] = "22",
		["崇"] = "22",
		["崇明"] = "22",
		["p"] = "浦江",
		["pjl"] = "浦江",
		["浦"] = "浦江",
		["m"] = "磁浮",
		["maglev"] = "磁浮",
		["磁"] = "磁浮",
	}
}

return p