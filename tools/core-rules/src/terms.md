# Tooltips (v1.13): game terms, terrain types, universal actions and weapon rules of the core rules.
# One term per line:  id | kind | Name | Russian name | definition | aliases
# kind: term, terrain, action, weapon. The definition is the official text of the core rules (this document),
# referenced, never retold: section[/heading][@Action][~text prefix][+N more units], several joined with ' & '.
# Aliases (comma-separated) are matched in the rendered text: # = a number or x, " = an inch mark (" ” ″),
# [a|b] = optional, {a|b} = one of, * = a few words, A>>B = A only when followed by B; prefixes: ^ = case-sensitive,
# @ = only in weapon rules of a datacard, ! = only in rules text. Weapon rules: case-sensitive in rules text,
# any case in the weapon rules of a datacard; the other kinds only in rules text.

control-range | term | Control range | Дистанция контроля | control-range~Many rules relate+1 | control range[s]
cover | term | Cover | Укрытие | cover~Cover is determined | in cover, cover
cover-save | term | Cover save | Спасбросок за укрытие | shoot~The defender collects three defence dice | cover save[s]
obscured | term | Obscured | Затенение | obscured~Obscured is determined & obscured~When an operative is shooting, if the target operative is obscured+2 | obscured, obscuring
valid-target | term | Valid target | Допустимая цель | valid-target~Some rules require you to select+2 | valid target[s]
visible | term | Visible | Видимость | visible~For something to be visible | visible, visibility
intervening | term | Intervening | Перекрытие | intervening~Rules such as cover and obscured | wholly intervening, intervening
targeting-lines | term | Targeting lines | Линии прицеливания | intervening~To use targeting lines | targeting line[s]
wholly-within | term | Within and wholly within | В пределах и полностью в пределах | distances~If a rule requires something to be ‘within’ | wholly within
incapacitated | term | Incapacitated | Выведен из строя | damage~When damage is inflicted | incapacitated, incapacitate[s]
injured | term | Wounded and injured | Ранен и тяжело ранен | damage~While an operative has fewer | injured, wounded
engage | term | Engage order | Приказ Engage («Бой») | orders~**Engage:** | ^Engage order[s], ^Engage
conceal | term | Conceal order | Приказ Conceal («Скрыт») | orders~**Conceal:** | ^Conceal order[s], ^Conceal
ready-expended | term | Ready and expended | Готов и отыгран | orders~Order tokens have two sides | expended, ready[ friendly| enemy] operative[s]
active-operative | term | Active operative | Активный оперативник | firefight~The operative performs actions | active operative[s]
counteract | term | Counteract | Контрдействие | firefight~When you would activate a ready friendly operative | counteraction[s], counteract[s|ing|ed]
apl | term | APL (Action point limit) | Лимит очков действий (APL) | datacards~**APL (Action point limit):** | ^APL
turning-point | term | Turning point | Ход (turning point) | intro~The main step of the game sequence | turning point[s]
initiative | term | Initiative | Инициатива | strategy~The player with initiative activates first | initiative
command-points | term | Command points (CP) | Очки командования (CP) | strategy~Each player gains 1 Command point | Command point[s], ^#CP, ^CP
strategic-gambit | term | STRATEGIC GAMBIT | Стратегический гамбит | strategy~Starting with the player who has initiative | ^STRATEGIC GAMBIT[S]
killzone-floor | term | Killzone floor | Пол килзоны | killzone-floor~The killzone floor | killzone floor
roll-off | term | Roll-off | Бросок-спор | roll-off~If a rule requires a roll-off | roll{-| }off[s]
re-roll | term | Re-roll | Переброс | dice~Some rules allow you to re-roll | re-roll[s|ed|ing]
successes | term | Normal and critical successes | Обычный и критический успех | shoot~The attacker rolls their attack dice | critical success[es], normal success[es]
contest | term | Contest and control (markers) | Оспаривание и контроль маркеров | markers~Operatives contest markers | contest[s|ing|ed]
free-action | term | Free action | Бесплатное действие | actions~Free actions can only be performed+3 | free action[s]
assist | term | Assist | Помощь в ближнем бою | fight~While a friendly operative is assisted | assist[s|ed|ing]

reposition | action | Reposition | Перемещение | actions@Reposition | ^Reposition
dash | action | Dash | Рывок | actions@Dash | ^Dash
fall-back | action | Fall Back | Отступление | actions@Fall Back | ^Fall Back
charge | action | Charge | Натиск (Charge) | actions@Charge | ^Charge
pick-up-marker | action | Pick Up Marker | Подобрать маркер | actions@Pick Up Marker | ^Pick Up Marker
place-marker | action | Place Marker | Положить маркер | actions@Place Marker | ^Place Marker

heavy-terrain | terrain | Heavy terrain | Тяжёлая местность | terrain-types/heavy | ^Heavy>> terrain, ^Heavy>> cover
light-terrain | terrain | Light terrain | Лёгкая местность | terrain-types/light | ^Light>> terrain, ^Light>> cover
blocking-terrain | terrain | Blocking terrain | Блокирующая местность | terrain-types/blocking | ^Blocking>> terrain, ^Blocking>> and
vantage-terrain | terrain | Vantage terrain | Возвышенность (Vantage) | terrain-types/vantage~Vantage terrain is the upper levels+4 | ^Vantage
accessible-terrain | terrain | Accessible terrain | Проходимая местность | terrain-types/accessible | ^Accessible
insignificant-terrain | terrain | Insignificant terrain | Незначительная местность | terrain-types/insignificant | ^Insignificant
exposed-terrain | terrain | Exposed terrain | Открытая местность | terrain-types/exposed | ^Exposed
ceiling-terrain | terrain | Ceiling terrain | Потолок (Ceiling) | terrain-types/ceiling | ^Ceiling
climb | terrain | Climbing | Подъём | terrain-movement/climbing | climb[s|ing|ed]
drop | terrain | Dropping | Спуск | terrain-movement/dropping | drop[s|ping|ped]>>{ down| off| from| or| and|/|,|.}
jump | terrain | Jumping | Прыжок | terrain-movement/jumping | jump[s|ing|ed]

weapon-accurate-x | weapon | Accurate x | Точное x | weapon-rules/accurate-x | Accurate #, Accurate
weapon-balanced | weapon | Balanced | Сбалансированное | weapon-rules/balanced | Balanced
weapon-blast-x | weapon | Blast x | Взрыв x | weapon-rules/blast-x | Blast #", Blast
weapon-brutal | weapon | Brutal | Жестокое | weapon-rules/brutal | Brutal
weapon-ceaseless | weapon | Ceaseless | Неустанное | weapon-rules/ceaseless | Ceaseless
weapon-devastating-x | weapon | Devastating x | Опустошающее x | weapon-rules/devastating-x | #" Devastating #, Devastating #, Devastating
weapon-heavy | weapon | Heavy | Тяжёлое | weapon-rules/heavy | Heavy (* only), @Heavy, !Heavy>> weapon rule
weapon-hot | weapon | Hot | Перегрев | weapon-rules/hot | Hot
weapon-lethal-x | weapon | Lethal x+ | Смертоносное x+ | weapon-rules/lethal-x | Lethal #+, Lethal
weapon-limited-x | weapon | Limited x | Ограниченное x | weapon-rules/limited-x | Limited #, !Limited>> weapon rule
weapon-piercing-x | weapon | Piercing x | Пробивающее x | weapon-rules/piercing-x | Piercing Crits #, Piercing #, Piercing Crits, Piercing
weapon-punishing | weapon | Punishing | Карающее | weapon-rules/punishing | Punishing
weapon-range-x | weapon | Range x | Дальность x | weapon-rules/range-x | Range #", @Range #, !Range x
weapon-relentless | weapon | Relentless | Беспощадное | weapon-rules/relentless | Relentless
weapon-rending | weapon | Rending | Разрывающее | weapon-rules/rending | Rending
weapon-saturate | weapon | Saturate | Насыщающее | weapon-rules/saturate | Saturate
weapon-seek | weapon | Seek | Ищущее | weapon-rules/seek | Seek Light, Seek
weapon-severe | weapon | Severe | Суровое | weapon-rules/severe | Severe
weapon-shock | weapon | Shock | Шок | weapon-rules/shock | Shock
weapon-silent | weapon | Silent | Бесшумное | weapon-rules/silent | Silent
weapon-stun | weapon | Stun | Оглушающее | weapon-rules/stun | Stun
weapon-torrent-x | weapon | Torrent x | Поток x | weapon-rules/torrent-x | Torrent #", Torrent
