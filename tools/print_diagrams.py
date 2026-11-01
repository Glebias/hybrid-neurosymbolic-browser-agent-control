"""Print layouts of the same eight approved diagrams, with shorter labels.
The detailed screen originals remain available. No additional report figures.
"""
import html
import sys
from pathlib import Path

class SVG:
    def __init__(self,w,h,title):
        self.w,self.h=w,h
        self.parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
          '<style>text{font-family:"Times New Roman",serif;font-size:23px;fill:#000}.label{paint-order:stroke;stroke:#fff;stroke-width:5;stroke-linejoin:round}.head{font-size:27px;font-weight:bold}.small{font-size:20px}.line{fill:none;stroke:#000;stroke-width:2}</style>',
          '<defs><marker id="filled" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="#000"/></marker><marker id="open" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M1 1 L9 5 L1 9" fill="none" stroke="#000" stroke-width="1.5"/></marker></defs>',f'<rect width="{w}" height="{h}" fill="#fff"/>']
        # The report supplies the figure caption; keep a non-rendered accessible title only.
        self.parts.append(f'<title>{html.escape(title)}</title>')
    def text(self,x,y,text,cls='',anchor='middle'):
        lines=text.split('\n')
        for i,line in enumerate(lines):self.parts.append(f'<text class="{cls}" x="{x}" y="{y+i*27}" text-anchor="{anchor}">{html.escape(line)}</text>')
    def rect(self,x,y,w,h,label='',dash=False,fill='#fff'):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="#000" stroke-width="2"'+(' stroke-dasharray="9 7"' if dash else '')+'/>')
        if label:self.text(x+w/2,y+h/2-13*(len(label.split('\n'))-1)+8,label)
    def path(self,d,arrow=False,dashed=False,open=False):
        self.parts.append(f'<path class="line" d="{d}"'+(' stroke-dasharray="8 6"' if dashed else '')+(f' marker-end="url(#{"open" if open else "filled"})"' if arrow else '')+'/>')
    def ellipse(self,x,y,rx,ry,label):
        self.parts.append(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="#fff" stroke="#000" stroke-width="2"/>');self.text(x,y+8,label)
    def diamond(self,x,y,w,h,label):
        self.parts.append(f'<path d="M{x} {y-h/2} L{x+w/2} {y} L{x} {y+h/2} L{x-w/2} {y} Z" fill="#fff" stroke="#000" stroke-width="2"/>');self.text(x,y-5,label)
    def message(self,x1,x2,y,label,reply=False):
        self.path(f'M{x1} {y} H{x2}',True,reply,reply);self.text((x1+x2)/2,y-12,label,'label small')
    def participants(self,labels):
        xs=[75+180*i for i in range(len(labels))] if len(labels)==6 else [90+215*i for i in range(len(labels))]
        for x,label in zip(xs,labels):
            self.rect(x-72,75,144,70,label);self.path(f'M{x} 145 V{self.h-40}',dashed=True)
        return xs
    def save(self,p):p.write_text('\n'.join(self.parts+['</svg>']),encoding='utf-8')

def generate(out):
    out.mkdir(parents=True,exist_ok=True)
    s=SVG(1050,660,'Возможности пользователя платформы')
    s.parts.append('<style>text{font-size:27px}.small{font-size:24px}</style>')
    s.rect(270,65,750,575);s.text(645,98,'Платформа управления и защиты', 'small')
    s.parts.append('<circle cx="100" cy="300" r="24" class="line"/>');s.path('M100 324 V400 M55 350 H145 M100 400 L60 460 M100 400 L140 460');s.text(100,498,'Пользователь','small')
    labels=['Подключить агента','Поставить задачу','Наблюдать выполнение','Посмотреть результат','Подтвердить или отклонить','Настроить правила','Просмотреть журнал']
    for i,label in enumerate(labels):
        y=155+i*75;s.ellipse(650,y,285,29,label);s.path(f'M145 350 L365 {y}')
    s.save(out/'01_варианты_использования.svg')

    s=SVG(1050,940,'Архитектура платформы и защитного слоя')
    s.rect(35,75,220,70,'Пользователь');s.rect(755,75,250,70,'Веб-панель')
    s.path('M255 110 H755',True);s.text(500,96,'задача, правила, согласие','label small')
    s.rect(25,210,430,300,dash=True);s.text(240,240,'Процесс агента')
    s.rect(55,280,160,80,'Browser\nUse');s.rect(260,280,165,80,'Защищённые\nинструменты');s.path('M215 320 H260',True)
    s.rect(55,410,160,70,'Браузер');s.path('M342 360 V445 H215',True);s.text(320,395,'ALLOW','label small')
    s.rect(500,210,525,560,dash=True);s.text(760,240,'Локальный сервис')
    s.rect(545,290,190,80,'Задачи\nи события');s.rect(790,290,190,80,'Координатор\nпроверки')
    s.path('M790 310 H735',True)
    s.path('M880 145 V290',True);s.path('M545 320 H455 V265 H135 V280',True);s.text(330,254,'цель задачи','label small')
    s.path('M425 310 H480 V385 H820 V370',True);s.text(660,409,'действие и контекст','label small')
    s.path('M790 345 H755 V470 H400 V360',True);s.text(610,460,'решение','label small')
    s.rect(545,525,190,75,'Смысловой\nанализ');s.rect(790,525,190,75,'Символьный\nрешатель');s.path('M885 370 V490 H640 V525',True);s.path('M735 565 H790',True)
    s.rect(545,805,190,75,'Внешняя\nмодель');s.rect(790,665,190,70,'Правила\nи журнал');s.path('M640 600 V805',True);s.path('M640 805 V600',True);s.path('M885 600 V665',True);s.path('M885 665 V600',True)
    s.path('M980 565 H1005 V330 H980',True)
    s.save(out/'02_общая_архитектура.svg')

    s=SVG(1050,960,'Проверка действия до исполнения')
    a,b,c,d,e,f=s.participants(['Агент','Адаптер','Сервис','Модель','Решатель','Инструмент'])
    for x1,x2,y,label,reply in [(a,b,195,'действие',False),(b,c,270,'контекст',False),(c,d,345,'анализ',False),(d,c,420,'признаки',True),(c,e,495,'факты и правила',False),(e,c,570,'вердикт',True),(c,b,645,'решение',True),(b,f,750,'только ALLOW',False),(f,b,825,'результат',True),(b,a,900,'результат / отказ',True)]:s.message(x1,x2,y,label,reply)
    s.save(out/'04_последовательность_проверки.svg')

    s=SVG(1000,1280,'Алгоритм нейросимвольного решения')
    s.ellipse(350,95,160,34,'Предложение')
    s.path('M350 129 V175',True);s.rect(140,175,420,70,'Проверка формата и контекста')
    s.path('M350 245 V280',True);s.diamond(350,330,390,100,'Поддерживается\nи контекст получен?')
    s.path('M545 330 H680',True);s.text(610,316,'нет','label small');s.rect(680,300,260,60,'BLOCK')
    s.path('M350 380 V420',True);s.text(375,405,'да','small');s.diamond(350,470,390,100,'Обязательный или\nпользовательский запрет?')
    s.path('M545 470 H680',True);s.text(610,456,'да','label small');s.rect(680,440,260,60,'BLOCK')
    s.path('M350 520 V560',True);s.text(375,547,'нет','small');s.diamond(350,610,390,100,'Проверенное\nнаблюдение?')
    s.path('M545 610 H680',True);s.text(610,596,'да','label small');s.rect(680,580,260,60,'ALLOW')
    s.path('M350 660 V710',True);s.text(375,690,'нет','small');s.rect(140,710,420,70,'Смысловой анализ моделью')
    s.path('M350 780 V825',True);s.diamond(350,875,390,100,'Ответ корректен?')
    s.path('M545 875 H680',True);s.text(610,860,'нет','label small');s.rect(680,845,260,60,'BLOCK')
    s.path('M350 925 V970',True);s.text(375,950,'да','small');s.rect(140,970,420,85,'Применение приоритетов\nк фактам и правилам')
    s.path('M350 1055 V1110',True);s.ellipse(350,1150,260,42,'ALLOW / ASK_USER / BLOCK')
    s.save(out/'05_алгоритм_решения.svg')

    s=SVG(1050,820,'Логическая модель данных')
    boxes=[('Агент',['agent_id, тип','состояние, профиль']),('Профиль',['profile_id, версия','режим подтверждений']),('Правило',['rule_id, версия','условие, приоритет, исход']),('Задача',['task_id, agent_id','цель, статус, результат']),('Действие',['proposal_id, task_id','инструмент, контекст']),('Смысловая оценка',['эффект, полномочия','свидетельство, риск']),('Подтверждение',['decision_id, срок','ответ, время ответа']),('Решение',['decision_id, proposal_id','исход, причина, задержка']),('Событие',['seq, task_id, decision_id?','время, вид, результат'])]
    for i,(title,fields) in enumerate(boxes):
        x=25+(i%3)*355;y=100+(i//3)*235;s.rect(x,y,290,160);s.text(x+145,y+32,title);s.path(f'M{x} {y+47} H{x+290}')
        for j,field in enumerate(fields):s.text(x+15,y+87+j*34,field,'small','start')
    for y,left,right in [(180,'N:1','N:M'),(415,'1:N','1:0..1'),(650,'0..1:1','1:0..N')]:
        s.path(f'M315 {y} H380 M670 {y} H735');s.text(345,y-10,left,'small');s.text(705,y-10,right,'small')
    s.path('M170 260 V335 M525 495 V570');s.text(187,305,'1:N','small');s.text(542,541,'1:N','small')
    s.save(out/'06_модель_данных.svg')

    s=SVG(1000,930,'Подключение Browser Use к защитному слою')
    s.rect(250,80,500,75,'Задача пользователя из панели');s.path('M500 155 V205',True)
    s.rect(250,205,500,95,'Создание Agent с GuardedTools\nдо запуска агентского цикла');s.path('M500 300 V350',True)
    s.rect(250,350,500,85,'Предложение инструмента\nначальное или обычное');s.path('M500 435 V485',True)
    s.rect(250,485,500,80,'GuardedTools.act: контекст\nи запрос в локальный сервис');s.path('M500 565 V620',True)
    s.rect(250,620,500,70,'Решение сервиса')
    s.path('M500 690 V735 H165 M500 735 H835');s.path('M165 735 V780',True);s.path('M500 735 V780',True);s.path('M835 735 V780',True)
    s.rect(25,780,280,95,'ALLOW\nисходный Tools.act');s.rect(360,780,280,95,'ASK_USER\nожидание согласия');s.rect(695,780,280,95,'BLOCK\nотказ в цикл агента')
    s.save(out/'09_встраивание_в_browser_use.svg')

    s=SVG(1050,1120,'Подтверждение и ограниченный срок ожидания')
    a,b,c,d,e,f=s.participants(['Агент','Адаптер','Сервис','Панель','Человек','Инструмент'])
    for x1,x2,y,label,reply in [(a,b,190,'действие',False),(b,c,260,'проверить',False),(c,b,330,'ASK_USER',True),(d,c,400,'ожидающие',False),(c,d,470,'запрос',True),(e,d,540,'ответ',False),(d,c,610,'согласие / отказ',False),(b,c,680,'получить ответ',False),(c,b,750,'исход',True)]:s.message(x1,x2,y,label,reply)
    s.rect(25,790,1000,270,fill='none');s.text(40,818,'alt: согласие и актуальный контекст','small','start')
    s.message(b,f,865,'исполнить');s.message(f,b,925,'результат',True)
    s.path('M25 955 H1025',dashed=True);s.text(40,983,'else: отказ, истечение срока или изменение контекста','small','start');s.message(b,a,1030,'отказ без исполнения',True)
    s.save(out/'22_ожидание_подтверждения_и_тайм_аут.svg')

    s=SVG(1050,1030,'Задача из панели и получение результата')
    a,b,c,d,e=s.participants(['Человек','Панель','Сервис','Агент','Защищённые\nинструменты'])
    for x1,x2,y,label,reply in [(a,b,200,'задача',False),(b,c,270,'создать',False),(c,b,340,'номер задачи',True),(d,c,410,'получить задачу',False),(c,d,480,'цель и профиль',True),(d,e,550,'действие',False),(e,c,620,'проверить',False),(c,e,690,'решение',True),(e,d,760,'результат / отказ',True),(d,c,830,'итог задачи',False),(b,c,900,'состояние',False),(c,b,970,'ход и результат',True)]:s.message(x1,x2,y,label,reply)
    s.save(out/'25_задача_через_панель_и_результат.svg')

if __name__=='__main__':generate(Path(sys.argv[1]))
